# 数据管理模块 - 按 user_id 隔离的数据持久化与共享

import os
import shutil
import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# 数据缓存根目录
_CACHE_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_plots")


def _detect_encoding(file_obj) -> str:
    """自动检测文件编码
    
    优先尝试 UTF-8, 然后尝试 GBK/GB2312 (中文Windows常见),
    最后尝试 Latin-1 (兼容性最强)
    """
    encodings_to_try = ['utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']
    
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
def get_data_manager(user_id: int):
    """获取指定用户的数据管理器（按 user_id 隔离）"""
    return DataManager(user_id)

# 便捷函数：自动获取当前登录用户的 DataManager
def get_current_dm() -> 'DataManager':
    """获取当前登录用户的数据管理器（便捷函数）"""
    from billing.auth import get_current_user
    user = get_current_user()
    if not user:
        raise RuntimeError("用户未登录，无法获取数据管理器")
    return get_data_manager(user['id'])


class DataManager:
    """按用户隔离的数据管理器，每个用户有独立的缓存文件"""

    def __init__(self, user_id: int):
        self._user_id = user_id
        self._data = None
        self._filename = None
        # 每个用户独立目录：temp_plots/user_{id}/
        self._cache_dir = os.path.join(_CACHE_ROOT, f"user_{user_id}")
        self._cache_file = os.path.join(self._cache_dir, "data.parquet")
        self._name_file = os.path.join(self._cache_dir, "data.name")
        self._load_from_disk()

    @property
    def user_id(self) -> int:
        return self._user_id

    def _load_from_disk(self):
        """从磁盘加载数据缓存"""
        try:
            if os.path.exists(self._cache_file):
                self._data = pd.read_parquet(self._cache_file)
                if os.path.exists(self._name_file):
                    with open(self._name_file, 'r', encoding='utf-8') as f:
                        self._filename = f.read().strip()
        except Exception as e:
            print(f"用户 {self._user_id} 加载数据缓存失败: {e}")
            self._data = None

    def _save_to_disk(self):
        """将数据持久化到磁盘"""
        try:
            os.makedirs(self._cache_dir, exist_ok=True)
            if self._data is not None:
                self._data.to_parquet(self._cache_file, index=False)
                if self._filename:
                    with open(self._name_file, 'w', encoding='utf-8') as f:
                        f.write(self._filename)
            elif os.path.exists(self._cache_file):
                os.remove(self._cache_file)
                if os.path.exists(self._name_file):
                    os.remove(self._name_file)
        except Exception as e:
            print(f"用户 {self._user_id} 保存数据缓存失败: {e}")

    def clear_cache_files(self):
        """清除磁盘上的缓存文件（退出登录时调用）"""
        try:
            if os.path.exists(self._cache_dir):
                shutil.rmtree(self._cache_dir)
        except Exception as e:
            print(f"用户 {self._user_id} 清除缓存文件失败: {e}")
    
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

    def get_all_categorical_columns(self) -> list:
        """获取所有分类型列名列表，包括数字型分类变量（如区组1,2,3...）

        数字型分类变量判定标准：
        - 所有值都是整数
        - 唯一值数量 >= 2
        """
        if self._data is None:
            return []
        base_cat = list(self._data.select_dtypes(include=['object', 'category']).columns)
        numeric_cats = []
        for col in self._data.select_dtypes(include=[np.number]).columns:
            uv = self._data[col].dropna().unique()
            if len(uv) >= 2 and all(float(v).is_integer() for v in uv):
                numeric_cats.append(col)
        return base_cat + numeric_cats

    def get_pure_numeric_columns(self) -> list:
        """获取纯数值型列名列表（排除数字型分类变量）"""
        if self._data is None:
            return []
        all_cat = set(self.get_all_categorical_columns())
        return [c for c in self._data.select_dtypes(include=[np.number]).columns if c not in all_cat]
    
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


def _clear_analysis_keys():
    """上传新数据后清除各分析页面缓存的参数 key，避免旧列名与新数据不匹配"""
    prefixes = (
        'crd_', 'rcbd_', 'latin_', 'split_', 'factorial_',
        'met_', 'alpha_', 'augmented_', 'interval_',
        'desc_', 'hyp_', 'reg_', 'multi_', 'vis_', 'exp_',
        'dm_example',
    )
    keys_to_remove = [k for k in list(st.session_state.keys())
                      if k.startswith(prefixes)]
    for k in keys_to_remove:
        del st.session_state[k]


def render_data_manager(expanded=None):
    """渲染数据管理组件

    Args:
        expanded: None=不折叠模式，True/False=控制expander状态
                  如为None则不使用expander，直接展示全部内容
    """

    dm = get_current_dm()
    uploader_key = '_file_uploader'
    
    # 使用 expander 或直接展示
    container = st.expander("📁 **数据管理**",
        expanded=(expanded if expanded is not None else not dm.is_loaded)) if expanded is not None else st.container()
    
    with container:
        col1, col2 = st.columns([1, 1])
        
        # ── 第一行：上传 | 示例数据 ──
        def _on_upload_change():
            """文件上传变化时自动加载新数据"""
            files = st.session_state.get(uploader_key)
            if files:
                f = files[-1] if isinstance(files, list) else files
                try:
                    dm.load_data(f, f.name)
                    st.session_state['_data_just_loaded'] = True
                except Exception as e:
                    st.session_state['_upload_error'] = str(e)
        
        with col1:
            uploaded_file = st.file_uploader(
                "**上传数据文件**",
                type=['csv', 'xlsx', 'xls'],
                help="支持CSV和Excel格式的数据文件",
                key=uploader_key,
                on_change=_on_upload_change
            )
        
        # 显示上传结果或错误
        if st.session_state.get('_data_just_loaded'):
            st.session_state.pop('_data_just_loaded', None)
            st.success(f"✅ 已加载: {dm.filename} ({dm.summary()['rows']} 行 × {dm.summary()['cols']} 列)")
        if st.session_state.get('_upload_error'):
            err = st.session_state.pop('_upload_error', None)
            st.error(f"❌ 加载失败: {err}")
        
        with col2:
            st.markdown("**选择示例数据**")
            example_option = st.selectbox(
                "选择示例数据",
                [
                    "完全随机设计",
                    "随机完全区组设计",
                    "拉丁方设计",
                    "裂区设计",
                    "两因素析因设计",
                    "MET多点试验",
                    "区试试验",
                    "Alpha不完全区组设计",
                    "增广设计",
                    "间比设计",
                ],
                label_visibility="collapsed",
                key="dm_example"
            )
            if st.button("📥 加载示例数据", width="stretch"):
                create_example_data(dm, example_option)
                st.success("✅ 示例数据已加载，请选择分析模块。")
        
        # ── 第二行：当前数据 | 数据操作 ──
        col3, col4 = st.columns([1, 1])
        with col3:
            if dm.is_loaded:
                st.markdown("""\
                <div style="border:1px solid #e2e8f0;border-radius:0.75rem;padding:1rem;background:#f8fafc;">
                    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">
                        <span style="font-size:1.25rem;">📄</span>
                        <span style="font-weight:600;font-size:0.95rem;color:#1e293b;">当前数据</span>
                    </div>
                    <div style="font-size:0.85rem;color:#64748b;word-break:break-all;">{filename}</div>
                </div>
                """.format(filename=dm.filename or "未命名"), unsafe_allow_html=True)
        with col4:
            if dm.is_loaded:
                csv_bytes = dm.data.to_csv(index=False).encode('utf-8-sig')
                base_name = os.path.splitext(dm.filename)[0] if dm.filename else "数据"
                if st.button("🗑️ 清除数据", width="stretch"):
                    dm.clear_data()
                    st.rerun()
                st.download_button(
                    label="💾 下载数据",
                    data=csv_bytes,
                    file_name=f"{base_name}.csv",
                    mime="text/csv",
                    width="stretch"
                )
    
    # 显示数据预览（如果有数据）
    if dm.is_loaded:
        with st.container():
            st.markdown("### 📋 数据预览")
            
            # 数据摘要（在表格上方）
            sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
            with sum_col1:
                st.metric("行数", dm.summary()["rows"])
            with sum_col2:
                st.metric("列数", dm.summary()["cols"])
            with sum_col3:
                st.metric("数值列", dm.summary()["numeric_cols"])
            with sum_col4:
                st.metric("缺失值", dm.summary()["missing_values"])
            
            # 数据表格（在摘要下方）
            if dm.data is not None:
                st.dataframe(dm.data, width="stretch")


def render_data_manager_expanded():
    """渲染全局数据管理组件（直接展开，无折叠）—— 委托给 render_data_manager"""
    render_data_manager(expanded=True)


def create_example_data(dm: DataManager, example_name: str = "随机区组数据"):
    """创建/加载示例田间试验数据供测试使用
    
    Args:
        dm: DataManager实例
        example_name: 示例数据名称
    """
    # 尝试从 data 目录加载 CSV 文件
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    
    # 匹配CSV文件名：名称后加"示例数据"
    csv_name = f"{example_name}示例数据.csv"
    
    csv_path = os.path.join(data_dir, csv_name)
    if os.path.exists(csv_path):
        encoding = _detect_encoding(csv_path)
        df = pd.read_csv(csv_path, encoding=encoding)
        dm.set_data(df, f"示例_{csv_name}")
    else:
        st.error(f"示例数据文件不存在: {csv_path}")