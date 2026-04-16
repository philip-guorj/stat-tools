# 数据管理模块 - 全局数据持久化与共享

import os
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# 全局数据缓存路径
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_plots")
CACHE_FILE = os.path.join(CACHE_DIR, "_global_data_cache.parquet")


def _detect_encoding(file_obj) -> str:
    """自动检测文件编码
    
    优先尝试 UTF-8, 然后尝试 GBK/GB2312 (中文Windows常见),
    最后尝试 Latin-1 (兼容性最强)
    """
    encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    
    # 如果是文件路径
    if isinstance(file_obj, str):
        for enc in encodings_to_try:
            try:
                with open(file_obj, 'r', encoding=enc) as f:
                    f.read(10000)  # 尝试读取前10000字符
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue
        return 'utf-8'  # 默认返回
    
    # 如果是文件对象 (UploadedFile)
    try:
        # 保存当前位置
        pos = file_obj.tell()
        # 尝试读取一部分来检测编码
        raw_bytes = file_obj.read(10000)
        file_obj.seek(pos)  # 恢复位置
        
        for enc in encodings_to_try:
            try:
                raw_bytes.decode(enc)
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue
    except Exception:
        pass
    
    return 'utf-8'


def _read_csv_with_encoding(file_obj, encoding=None):
    """使用正确的编码读取CSV文件"""
    if encoding is None:
        encoding = _detect_encoding(file_obj)
    
    try:
        if isinstance(file_obj, str):
            return pd.read_csv(file_obj, encoding=encoding)
        else:
            return pd.read_csv(file_obj, encoding=encoding)
    except Exception as e:
        # 如果指定编码仍然失败，尝试其他编码
        for enc in ['gbk', 'gb2312', 'gb18030', 'latin-1', 'utf-8-sig']:
            if enc != encoding:
                try:
                    if isinstance(file_obj, str):
                        return pd.read_csv(file_obj, encoding=enc)
                    else:
                        # 需要重置文件指针
                        file_obj.seek(0)
                        return pd.read_csv(file_obj, encoding=enc)
                except Exception:
                    continue
        raise e

@st.cache_resource
def get_data_manager():
    """获取全局数据管理器（单例模式）"""
    return DataManager()

class DataManager:
    """全局数据管理器，负责数据的持久化和跨页面共享"""
    
    def __init__(self):
        self._data = None
        self._filename = None
        self._load_from_disk()
    
    def _load_from_disk(self):
        """从磁盘加载数据缓存"""
        try:
            if os.path.exists(CACHE_FILE):
                self._data = pd.read_parquet(CACHE_FILE)
                # 尝试读取文件名信息
                name_file = CACHE_FILE + ".name"
                if os.path.exists(name_file):
                    with open(name_file, 'r', encoding='utf-8') as f:
                        self._filename = f.read().strip()
        except Exception as e:
            print(f"加载缓存失败: {e}")
            self._data = None
    
    def _save_to_disk(self):
        """将数据持久化到磁盘"""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            if self._data is not None:
                self._data.to_parquet(CACHE_FILE, index=False)
                # 保存文件名
                name_file = CACHE_FILE + ".name"
                if self._filename:
                    with open(name_file, 'w', encoding='utf-8') as f:
                        f.write(self._filename)
            elif os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
                name_file = CACHE_FILE + ".name"
                if os.path.exists(name_file):
                    os.remove(name_file)
        except Exception as e:
            print(f"保存缓存失败: {e}")
    
    @property
    def data(self) -> pd.DataFrame | None:
        """获取当前数据"""
        return self._data
    
    @property
    def filename(self) -> str | None:
        """获取当前文件名"""
        return self._filename
    
    @property
    def is_loaded(self) -> bool:
        """检查是否有数据已加载"""
        return self._data is not None and len(self._data) > 0
    
    def load_data(self, file_obj, filename: str = None) -> pd.DataFrame:
        """上传/加载数据文件
        
        Args:
            file_obj: 文件对象 (UploadedFile 或文件路径)
            file_name: 文件名
            
        Returns:
            加载的DataFrame
        """
        try:
            if isinstance(file_obj, str):
                # 文件路径
                if file_obj.endswith('.csv'):
                    self._data = _read_csv_with_encoding(file_obj)
                elif file_obj.endswith(('.xlsx', '.xls')):
                    self._data = pd.read_excel(file_obj)
                else:
                    raise ValueError("不支持的文件格式")
                self._filename = os.path.basename(file_obj)
            else:
                # UploadedFile 对象
                ext = os.path.splitext(filename or file_obj.name)[1].lower()
                if ext == '.csv':
                    self._data = _read_csv_with_encoding(file_obj)
                elif ext in ('.xlsx', '.xls'):
                    self._data = pd.read_excel(file_obj)
                else:
                    raise ValueError("不支持的文件格式，请使用 CSV 或 Excel 文件")
                self._filename = filename or file_obj.name
            
            self._save_to_disk()
            return self._data
            
        except Exception as e:
            st.error(f"加载数据失败: {e}")
            raise
    
    def set_data(self, df: pd.DataFrame, filename: str = "processed_data"):
        """直接设置数据（用于数据处理后的结果）"""
        self._data = df.copy()
        self._filename = filename
        self._save_to_disk()
    
    def clear_data(self):
        """清除当前数据"""
        self._data = None
        self._filename = None
        self._save_to_disk()
    
    def get_columns(self) -> list:
        """获取列名列表"""
        if self._data is not None:
            return list(self._data.columns)
        return []
    
    def get_numeric_columns(self) -> list:
        """获取数值型列名列表"""
        if self._data is not None:
            return list(self._data.select_dtypes(include=[np.number]).columns)
        return []
    
    def get_categorical_columns(self) -> list:
        """获取分类型列名列表"""
        if self._data is not None:
            return list(self._data.select_dtypes(include=['object', 'category']).columns)
        return []
    
    def preview(self, n_rows: int = 10) -> pd.DataFrame | None:
        """预览前n行数据"""
        if self._data is not None:
            return self._data.head(n_rows)
        return None
    
    def summary(self) -> dict:
        """返回数据摘要信息"""
        if self._data is None:
            return {"loaded": False}
        
        return {
            "loaded": True,
            "filename": self._filename,
            "rows": len(self._data),
            "cols": len(self._data.columns),
            "numeric_cols": len(self.get_numeric_columns()),
            "categorical_cols": len(self.get_categorical_columns()),
            "memory_usage": self._data.memory_usage(deep=True).sum(),
            "missing_values": int(self._data.isnull().sum().sum()),
            "columns": list(self._data.columns)
        }


def render_data_manager():
    """渲染全局数据管理组件（在所有页面显示）"""
    
    dm = get_data_manager()
    
    with st.expander("📁 **数据管理**", expanded=not dm.is_loaded):
        col1, col2 = st.columns([1, 1])
        
        with col1:
            uploaded_file = st.file_uploader(
                "上传数据文件 (CSV/Excel)",
                type=['csv', 'xlsx', 'xls'],
                help="支持CSV和Excel格式的数据文件"
            )
            
            if uploaded_file is not None:
                try:
                    dm.load_data(uploaded_file, uploaded_file.name)
                    st.success(f"✅ 已加载: {uploaded_file.name} ({dm.summary()['rows']} 行 × {dm.summary()['cols']} 列)")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 加载失败: {e}")
        
        with col2:
            if dm.is_loaded:
                st.markdown("**当前数据**")
                st.info(f"📄 {dm.filename}\n\n{dm.summary()['rows']} 行 × {dm.summary()['cols']} 列")
                
                if st.button("🗑️ 清除数据", use_container_width=True):
                    dm.clear_data()
                    st.rerun()
            
            # 示例数据选择
            st.markdown("---")
            st.markdown("**快速开始**")
            example_option = st.selectbox(
                "选择示例数据",
                ["随机区组数据", "MET试验"],
                label_visibility="collapsed"
            )
            if st.button("📥 加载示例数据", use_container_width=True):
                create_example_data(dm, example_option)
                st.rerun()
    
    # 显示数据预览（如果有数据）
    if dm.is_loaded:
        with st.container():
            st.markdown("### 📋 数据预览")
            preview_df = dm.preview(8)
            if preview_df is not None:
                st.dataframe(preview_df, use_container_width=True)
                
                # 数据摘要
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                with sum_col1:
                    st.metric("行数", dm.summary()["rows"])
                with sum_col2:
                    st.metric("列数", dm.summary()["cols"])
                with sum_col3:
                    st.metric("数值列", dm.summary()["numeric_cols"])
                with sum_col4:
                    st.metric("缺失值", dm.summary()["missing_values"])


def render_data_manager_expanded():
    """渲染全局数据管理组件（直接展开，无折叠）"""
    
    dm = get_data_manager()
    
    st.markdown("### 📁 数据管理")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "上传数据文件 (CSV/Excel)",
            type=['csv', 'xlsx', 'xls'],
            help="支持CSV和Excel格式的数据文件"
        )
        
        if uploaded_file is not None:
            try:
                dm.load_data(uploaded_file, uploaded_file.name)
                st.success(f"✅ 已加载: {uploaded_file.name} ({dm.summary()['rows']} 行 × {dm.summary()['cols']} 列)")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 加载失败: {e}")
    
    with col2:
        if dm.is_loaded:
            st.markdown("**当前数据**")
            st.info(f"📄 {dm.filename}\n\n{dm.summary()['rows']} 行 × {dm.summary()['cols']} 列")
            
            if st.button("🗑️ 清除数据", use_container_width=True):
                dm.clear_data()
                st.rerun()
        
        # 示例数据选择
        st.markdown("---")
        st.markdown("**快速开始**")
        example_option = st.selectbox(
            "选择示例数据",
            ["随机区组数据", "MET试验"],
            label_visibility="collapsed"
        )
        if st.button("📥 加载示例数据", use_container_width=True):
            create_example_data(dm, example_option)
            st.rerun()
    
    # 显示数据预览（如果有数据）
    if dm.is_loaded:
        with st.container():
            st.markdown("### 📋 数据预览")
            preview_df = dm.preview(8)
            if preview_df is not None:
                st.dataframe(preview_df, use_container_width=True)
                
                # 数据摘要
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                with sum_col1:
                    st.metric("行数", dm.summary()["rows"])
                with sum_col2:
                    st.metric("列数", dm.summary()["cols"])
                with sum_col3:
                    st.metric("数值列", dm.summary()["numeric_cols"])
                with sum_col4:
                    st.metric("缺失值", dm.summary()["missing_values"])


def create_example_data(dm: DataManager, example_name: str = "随机区组数据"):
    """创建/加载示例田间试验数据供测试使用
    
    Args:
        dm: DataManager实例
        example_name: 示例数据名称，可选 "随机区组数据" 或 "MET试验"
    """
    if example_name == "MET试验":
        # 从data目录加载MET多点试验数据
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        csv_path = os.path.join(data_dir, "MET试验.csv")
        if os.path.exists(csv_path):
            encoding = _detect_encoding(csv_path)
            df = pd.read_csv(csv_path, encoding=encoding)
            dm.set_data(df, "示例_MET试验.csv")
        else:
            st.error("示例数据文件不存在")
        return
    
    # 默认：创建RCBD随机区组示例数据
    np.random.seed(42)
    treatments = ['品种A', '品种B', '品种C', '品种D']
    blocks = ['区组I', '区组II', '区组III']
    
    data = []
    for treatment in treatments:
        for block in blocks:
            base_yield = {'品种A': 85, '品种B': 92, '品种C': 78, '品种D': 88}[treatment]
            block_effect = {'区组I': 0, '区组II': -3, '区组III': 5}[block]
            yield_val = base_yield + block_effect + np.random.normal(0, 5)
            data.append({
                '处理': treatment,
                '区组': block,
                '产量': round(yield_val, 2),
                '株高': round(yield_val * 0.85 + np.random.normal(10, 3), 1),
                '穗长': round(np.random.uniform(15, 25), 1),
                '千粒重': round(np.random.uniform(35, 45), 1)
            })
    
    df = pd.DataFrame(data)
    dm.set_data(df, "示例_随机区组产量数据.csv")