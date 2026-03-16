import argparse
import logging
import pickle
import shutil
from pathlib import Path

import lmdb
import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem
from tqdm import tqdm

# 禁用 RDKit 的多余警告
RDLogger.DisableLog('rdApp.*')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ==================== LMDB 工具函数 ====================

def write_lmdb(data, lmdb_path, force_recreate=True):
    """写入 LMDB 数据库"""
    if force_recreate and Path(lmdb_path).exists():
        if Path(lmdb_path).is_dir():
            shutil.rmtree(lmdb_path)
        else:
            Path(lmdb_path).unlink()
    
    env = lmdb.open(
        str(lmdb_path),
        subdir=False,
        readonly=False,
        lock=False,
        readahead=False,
        meminit=False,
        map_size=1099511627776,
    )
    
    idx = 0
    with env.begin(write=True) as txn:
        for d in data:
            txn.put(str(idx).encode('ascii'), pickle.dumps(d))
            idx += 1
    env.close()
    
    logger.info(f"✓ 写入 {idx} 条记录到 {lmdb_path}")


# ==================== PDB/SDF 处理函数 ====================

def read_pdb(pdb_path):
    """读取 PDB 文件，返回原子类型和坐标"""
    try:
        from biopandas.pdb import PandasPdb
    except ImportError:
        raise ImportError("缺少 biopandas 库，请使用 'pip install biopandas' 安装")
        
    pdb_df = PandasPdb().read_pdb(str(pdb_path))
    atom_df = pdb_df.df['ATOM']
    
    atom_types = atom_df['atom_name'].tolist()
    coordinates = atom_df[['x_coord', 'y_coord', 'z_coord']].values
    
    return {
        'atom_types': atom_types,
        'coordinates': coordinates,
    }


def gen_conformation(mol, num_conf=1, num_worker=1):
    """生成分子构象"""
    try:
        mol = Chem.AddHs(mol)
        AllChem.EmbedMultipleConfs(
            mol,
            numConfs=num_conf,
            numThreads=num_worker,
            pruneRmsThresh=1,
            maxAttempts=10000,
            useRandomCoords=False,
        )
        try:
            AllChem.MMFFOptimizeMoleculeConfs(mol, numThreads=num_worker)
        except Exception:
            pass
        mol = Chem.RemoveHs(mol)
    except Exception as e:
        logger.error(f"无法生成构象: {e}")
        return None
    
    if mol.GetNumConformers() == 0:
        return None
    
    return mol


def read_sdf_file(sdf_path):
    """读取 SDF 文件，返回分子列表"""
    suppl = Chem.SDMolSupplier(str(sdf_path), removeHs=True, sanitize=True)
    mols = [mol for mol in suppl if mol is not None]
    logger.info(f"  从 {sdf_path} 读取了 {len(mols)} 个有效分子")
    return mols


# ==================== 数据转换函数 ====================

def pocket_to_dict(pocket_name, pocket_pdb_path):
    """将 pocket PDB 转换为字典格式"""
    try:
        pocket_data = read_pdb(pocket_pdb_path)
        return {
            'pocket': pocket_name,
            'pocket_index': 0,
            'pocket_atoms': pocket_data['atom_types'],
            'pocket_coordinates': pocket_data['coordinates'],
        }
    except Exception as e:
        logger.error(f"解析 PDB 文件失败 {pocket_pdb_path}: {e}")
        return None


def ligand_to_dict(ligand_name, mol, pocket_name):
    """将 RDKit Mol 转换为字典格式"""
    try:
        # 生成构象（如果没有的话）
        if mol.GetNumConformers() == 0:
            mol = gen_conformation(mol, num_conf=1, num_worker=1)
            if mol is None:
                logger.warning(f"无法生成构象: {ligand_name}")
                return None
        
        coords = mol.GetConformer(0).GetPositions()
        atoms = [atom.GetSymbol() for atom in mol.GetAtoms()]
        smi = Chem.MolToSmiles(mol)
        
        return {
            'name': ligand_name,
            'atoms': atoms,
            'coordinates': [coords],  # LigUnity expects list of conformations
            'smi': smi,
            'mol': mol,
            'pocket': pocket_name,
        }
    except Exception as e:
        logger.error(f"转换配体失败 {ligand_name}: {e}")
        return None


# ==================== 主处理函数 ====================

def process_data_from_files(target_name, pocket_pdb_path, ligands_sdf_path, workdir):
    """
    直接读取指定的 PDB 和 SDF 文件路径生成 LMDB。
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    pocket_pdb_path = Path(pocket_pdb_path)
    ligands_sdf_path = Path(ligands_sdf_path)
    
    pockets = []
    ligands = []
    
    logger.info(f"开始处理 Target: {target_name}")
    
    # 1. 处理 pocket
    if not pocket_pdb_path.exists():
        logger.error(f"⚠️ pocket 文件不存在: {pocket_pdb_path}")
        return False
        
    pocket_dict = pocket_to_dict(target_name, pocket_pdb_path)
    if pocket_dict:
        pockets.append(pocket_dict)
    
    # 2. 处理 ligands
    if not ligands_sdf_path.exists():
        logger.error(f"⚠️ ligands 文件不存在: {ligands_sdf_path}")
        return False
        
    ligand_mols = read_sdf_file(ligands_sdf_path)
    target_ligand_count = 0
    
    for idx, mol in enumerate(tqdm(ligand_mols, desc="处理配体小分子")):
        # 使用 SDF 文件中的原始配体名称，如果没有则自动命名
        if mol.HasProp('_Name') and mol.GetProp('_Name').strip():
            ligand_name = mol.GetProp('_Name').strip()
        else:
            ligand_name = f"{target_name}_ligand_{idx}"
        
        ligand_dict = ligand_to_dict(ligand_name, mol, target_name)
        if ligand_dict is not None:
            ligands.append(ligand_dict)
            target_ligand_count += 1
            
    logger.info(f"✓ 解析完成 - Pocket: 1, Ligands: {target_ligand_count}")
    
    # 3. 写入 LMDB
    pocket_lmdb = workdir / "proteins.lmdb"
    ligand_lmdb = workdir / "ligands.lmdb"
    
    logger.info("正在写入 LMDB 文件...")
    write_lmdb(pockets, pocket_lmdb)
    write_lmdb(ligands, ligand_lmdb)
    
    logger.info(f"🎉 全部处理完成！LMDB 文件已保存至: {workdir.absolute()}")
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='独立生成 Pocket 和 Ligands 的 LMDB 数据库')
    parser.add_argument('-t', '--target', required=True, help='靶点/蛋白质的名称 (如: Target_A)')
    parser.add_argument('-p', '--pdb', required=True, help='蛋白质口袋的 PDB 文件路径')
    parser.add_argument('-s', '--sdf', required=True, help='配体小分子的 SDF 文件路径')
    parser.add_argument('-o', '--outdir', default='./lmdb_workspace', help='生成的 LMDB 文件保存目录 (默认: ./lmdb_workspace)')
    
    args = parser.parse_args()
    
    process_data_from_files(
        target_name=args.target,
        pocket_pdb_path=args.pdb,
        ligands_sdf_path=args.sdf,
        workdir=args.outdir
    )
