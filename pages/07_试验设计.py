# 试验设计模块 - 田间试验方案生成

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
from scipy import stats
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.styles import inject_css, inject_upload_i18n
from utils.visitor_logger import log_visit
from billing.billing import require_auth, check_billing, can_download


def create_text_input_with_file_import(
    label: str, 
    default_value: str = "", 
    height: int = 150,
    key: str = None,
    accepted_types: list = ['.csv', '.txt']
) -> str:
    """
    创建带有文件导入功能的文本输入框（按钮在下方，与文本框等宽）
    导入文件后，内容会替换文本框中的内容
    
    参数:
        label: 输入框标签
        default_value: 默认值
        height: 文本框高度
        key: 唯一标识
        accepted_types: 接受的文件类型
    
    返回:
        处理后的文本内容
    """
    # 生成唯一key
    base_key = key if key else label.replace(' ', '_')
    text_key = f"text_{base_key}"
    file_key = f"file_{base_key}"
    
    # 初始化存储 — 文件导入的延迟更新在 widget 之前应用
    pending_key = f"{text_key}_pending"
    if pending_key in st.session_state:
        st.session_state[text_key] = st.session_state.pop(pending_key)
    elif text_key not in st.session_state:
        st.session_state[text_key] = default_value
    
    _type = label.replace("（每行一个）", "").strip()
    
    # 文本输入框（使用 session_state 中的值）
    value = st.text_area(
        label,
        height=height,
        key=text_key,
        placeholder=f"每行输入一个{_type}，或点击下方按钮导入文件"
    )
    
    # 文件导入按钮放在文本框下方，与文本框等宽
    st.markdown(
        f"""
        <style>
        [data-testid="stFileUploaderDropzone"] span {{
            display: none;
        }}
        [data-testid="stFileUploaderDropzone"]::before {{
            content: f"拖拽或点击导入{_type}列表文件（支持 CSV/TXT）";
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
    uploaded_file = st.file_uploader(
        f"📁 导入{_type}列表文件；每行一个，没有表头",
        type=['csv', 'txt'],
        key=file_key,
        help="点击选择文件导入，文件编码建议 UTF-8 或 GBK"
    )
    
    # 处理文件导入
    if uploaded_file is not None:
        try:
            # 根据文件类型读取
            if uploaded_file.name.endswith('.csv'):
                # 尝试多种编码，header=None 表示没有列标题，从首行开始读取
                content = None
                for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                    try:
                        uploaded_file.seek(0)
                        df = pd.read_csv(uploaded_file, encoding=encoding, header=None)
                        if len(df.columns) > 0:
                            content = '\n'.join(df.iloc[:, 0].astype(str).tolist())
                        else:
                            uploaded_file.seek(0)
                            content = uploaded_file.getvalue().decode(encoding)
                        break
                    except (UnicodeDecodeError, Exception):
                        continue
                
                if content is None:
                    raise ValueError("无法识别文件编码，请保存为 UTF-8 格式")
            else:
                # TXT 文件，尝试多种编码
                content = None
                for encoding in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
                    try:
                        uploaded_file.seek(0)
                        content = uploaded_file.getvalue().decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                
                if content is None:
                    raise ValueError("无法识别文件编码，请保存为 UTF-8 格式")
            
            # 清理内容
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            final_content = '\n'.join(lines)
            
            # 暂存更新到 pending key，rerun 后在 widget 之前应用
            st.session_state[pending_key] = final_content
            
            st.success(f"✅ 成功导入 {len(lines)} 条数据")
            st.rerun()
            
        except Exception as e:
            st.error(f"导入失败：{str(e)}")
    
    return value


# ========== 通用小区号设置 ==========

def plot_number_settings(has_environment: bool = False, key_prefix: str = ""):
    """
    通用小区号设置 UI 组件，返回设置字典。

    参数:
        has_environment: 是否显示"环境/试点间增量"（MET等多点试验用）
        key_prefix: 控件 key 前缀，避免不同设计页面冲突

    返回:
        dict: {
            'prefix': 前缀字符串,
            'start': 起始数字,
            'intra_block': 区组/重复内增量,
            'inter_block': 区组/重复间增量,
            'inter_env': 环境间增量 (0 表示无)
        }
    """
    kp = f"pn_{key_prefix}" if key_prefix else "pn"
    with st.expander("🔢 小区号设置", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            pn_prefix = st.text_input("前缀", value="", key=f"{kp}_prefix",
                                       help="小区号前缀，如 P、A 等，可为空")
            pn_start = st.number_input("起始编号", min_value=0, max_value=9999, value=0,
                                        key=f"{kp}_start", help="起始小区号的数字部分")
        with c2:
            pn_intra = st.number_input("区组/重复内增量", min_value=1, max_value=100, value=1,
                                        key=f"{kp}_intra",
                                        help="同一区组内，相邻处理的编号增量")
            pn_inter = st.number_input("区组/重复间增量", min_value=0, max_value=9999, value=100,
                                        key=f"{kp}_inter",
                                        help="不同区组间的编号增量")
        if has_environment:
            pn_env = st.number_input("环境/试点间增量", min_value=0, max_value=99999, value=1000,
                                      key=f"{kp}_env",
                                      help="不同环境/试点间的编号增量")
        else:
            pn_env = 0

    return {
        'prefix': pn_prefix.strip(),
        'start': pn_start,
        'intra_block': pn_intra,
        'inter_block': pn_inter,
        'inter_env': pn_env,
    }


def calculate_plot_number(config: dict, rep_idx: int, treat_idx: int,
                          env_idx: int = 0) -> str:
    """
    根据小区号设置计算最终小区号。

    公式: 前缀 + 起始编号 + 环境间增量×环境序号 + 区组间增量×区组编号 + 区组内增量×处理序号

    参数:
        config: plot_number_settings() 返回的字典
        rep_idx: 区组/重复编号（从 1 开始，不减1）
        treat_idx: 处理在区组内的序号（从 1 开始，不减1）
        env_idx: 环境/试点序号（从 1 开始，默认 0 表示单点试验）
    """
    num = config['start']
    if env_idx > 0:
        num += config['inter_env'] * env_idx
    num += config['inter_block'] * rep_idx
    num += config['intra_block'] * treat_idx
    prefix = config['prefix']
    return f"{prefix}{num}" if prefix else str(num)


def render_experimental_design():
    require_auth()
    log_visit("试验设计")
    inject_css()
    inject_upload_i18n()
    st.markdown('<div class="section-header">🌾 试验设计</div>', unsafe_allow_html=True)
    
    # 功能简介下拉菜单
    with st.expander("📖 功能简介", expanded=False):
        st.markdown("""
        **试验设计**模块帮助您生成科学合理的田间试验方案，确保试验结果具有统计可比性。
        
        | 设计类型 | 特点 | 适用场景 |
        |---------|------|---------|
        | 完全随机设计 (CRD) | 处理完全随机分配 | 环境均匀的温室、盆栽试验 |
        | 随机区组设计 (RCBD) | 区组内随机，区组间可异 | 田间试验最常用 |
        | 拉丁方设计 (LSD) | 双向控制变异 | 存在两个方向梯度时 |
        | 裂区设计 (SPD) | 主副区不同精度 | 耕作方式等难以小面积实施 |
        | 条区设计 (SSD) | 两个方向条区 | 两个因素都需要大面积 |
        | MET多点试验 | 多地点联合试验 | 品种区域试验、稳定性分析 |
        | Alpha设计 | 不完全区组，高效控制变异 | 品种区试、处理数>20 |
        | Lattice设计 | 格子排列，平衡比较 | 处理数为完全平方数 |
        | 增广设计 | 对照有重复，测试无重复 | 新品种初级筛选 |
        | 对角线设计 | 对角线排列，控制梯度 | 土壤单向梯度明显 |
        | 间比法设计 | 顺序排列，计算相对产量 | 品种初筛、处理数多 |
        | 对比法设计 | 处理与相邻对照比较 | 品种比较、示范试验 |
        
        **随机化原则**：同一处理在田间不能连续出现在同一行/列，避免系统误差。
        """)
    
    design_type = st.selectbox(
        "选择试验设计类型",
        [
            "---",
            "🎲 完全随机设计 (CRD)",
            "📦 随机区组设计 (RCBD)",
            "🔲 拉丁方设计 (LSD)",
            "✂️ 裂区设计 (Split Plot)",
            "📊 条区设计 (Strip Plot)",
            "🌍 MET多点试验设计",
            "🧬 Alpha设计 (Alpha Lattice)",
            "🔲 Lattice设计 (格子设计)",
            "➕ 增广设计 (Augmented Design)",
            "📐 对角线设计 (Diagonal Design)",
            "📈 间比法设计",
            "⚖️ 对比法设计"
        ]
    )
    
    st.markdown("---")
    
    # 计费守卫：选择设计类型后检查并扣减次数
    if design_type != "---":
        check_billing("试验设计-" + design_type, {"design_type": design_type})
    
    if design_type == "---":
        st.info("👆 请从上方选择试验设计类型")
        show_design_guide()
        return
    
    elif "完全随机" in design_type:
        crd_design()
    
    elif "随机区组" in design_type:
        rcbd_design()
    
    elif "拉丁方" in design_type:
        lsd_design()
    
    elif "裂区" in design_type:
        split_plot_design()
    
    elif "条区" in design_type:
        strip_plot_design()
    
    elif "MET" in design_type:
        met_design()
    
    elif "Alpha" in design_type:
        alpha_lattice_design()
    
    elif "Lattice" in design_type:
        lattice_design()
    
    elif "增广" in design_type:
        augmented_design()
    
    elif "对角线" in design_type:
        diagonal_design()
    
    elif "间比法" in design_type:
        interval_test_design()
    
    elif "对比法" in design_type:
        contrast_design()


def show_design_guide():
    """显示试验设计指南"""
    st.markdown("### 📚 试验设计选择指南")

    st.markdown("""
    **按环境条件选择：**
    - 环境均匀（温室/实验室）→ **CRD 完全随机设计**
    - 存在单向梯度（如土壤肥力梯度）→ **RCBD 随机区组设计**（田间最常用）
    - 存在双向梯度 → **LSD 拉丁方设计**

    **按处理因素选择：**
    - 一个因素 → CRD/RCBD
    - 两个因素，精度要求不同（主处理需大面积）→ **SPD 裂区设计**
    - 两个因素，精度要求相同（两个因素都需大面积）→ **SSD 条区设计**

    **按试验规模选择：**
    - 品种数≤10，常规区试 → RCBD
    - 品种数为完全平方数（如9、16、25），需要平衡比较 → **Lattice格子设计**
    - 品种数10-30，需要更高精度 → **Alpha设计**
    - 品种数>30，初级筛选 → **增广设计** 或 **间比法**
    - 多点试验 → **MET多点试验设计**

    **按排列方式选择：**
    - 土壤单向梯度明显，希望处理沿梯度对角线分布 → **对角线设计**

    **按比较方式选择：**
    - 品种初筛、处理数多，对照间隔插入，用左右对照均值计算相对产量 → **间比法设计**
    - 品种比较试验、示范展示，每个处理与相邻对照直接比较 → **对比法设计**
    """)


def crd_design():
    """完全随机设计"""
    st.markdown("### 🎲 完全随机设计 (CRD)")
    
    st.info("""
    **完全随机设计**是最简单的田间试验设计。
    
    **适用场景**：试验单元间环境差异不大（温室、培养箱、实验室均匀田块）。
    
    **特点**：所有处理在全部重复中完全随机排列，不设区组。
    
    **输入**：处理名称列表 + 重复次数。
    
    **输出**：随机化排列结果表、田间排列可视化图。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        treatments = create_text_input_with_file_import(
            "处理名称（每行一个）", 
            "品种A\n品种B\n品种C\n品种D", 
            height=150,
            key="crd_treatments"
        )
        treatment_list = [t.strip() for t in treatments.split('\n') if t.strip()]
    
    with col2:
        n_reps = st.number_input("重复次数", min_value=2, max_value=20, value=3)
        use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
        check_constraint = st.checkbox("确保同一处理在不同重复间不出现在同一位置", value=True)
    
    pn_cfg = plot_number_settings(key_prefix="crd")
    
    if st.button("生成设计方案"):
        # 基于时钟生成随机种子
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 使用约束随机化生成
        df_design = generate_crd_with_constraint(treatment_list, n_reps, seed, check_constraint)
        
        # 根据小区号设置重新计算
        _pn_col = []
        for _, row in df_design.iterrows():
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=int(row['重复']), treat_idx=int(row['位置'])))
        df_design['小区号'] = _pn_col
        if '排列序号' in df_design.columns:
            df_design['排列序号'] = df_design['小区号']
        
        # 显示结果
        st.success(f"✅ 已生成 {len(treatment_list)} 处理 × {n_reps} 重复 = {len(df_design)} 个小区")
        
        # 布局显示
        st.markdown("#### 📋 随机化排列结果")
        st.dataframe(df_design[['排列序号', '处理', '重复']], use_container_width=True)
        
        # 显示各重复的排列对比
        if check_constraint:
            st.markdown("#### 📊 各重复排列位置检查")
            show_replicate_constraint_check(df_design, treatment_list, n_reps)
        
        # 可视化
        fig = visualize_field_layout(df_design, f"CRD设计 - {len(treatment_list)}处理×{n_reps}重复")
        st.plotly_chart(fig, use_container_width=True)
        
        # 下载
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "CRD设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def rcbd_design():
    """随机区组设计"""
    st.markdown("### 📦 随机区组设计 (RCBD)")
    
    st.info("""
    **随机完全区组设计**是田间试验**最常用**的设计方法。
    
    **适用场景**：存在已知方向的环境梯度（如土壤肥力从一端到另一端变化）。
    
    **特点**：每个区组内包含全部处理的随机排列，通过区组控制环境变异。
    
    **输入**：处理名称列表 + 区组(重复)数。
    
    **输出**：各区组内排列结果、田间排列可视化图、区组间位置约束检查。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        treatments = create_text_input_with_file_import(
            "处理名称（每行一个）", 
            "品种A\n品种B\n品种C\n品种D\n品种E\n品种F", 
            height=150,
            key="rcbd_treatments"
        )
        treatment_list = [t.strip() for t in treatments.split('\n') if t.strip()]
    
    with col2:
        n_blocks = st.number_input("区组数", min_value=2, max_value=20, value=3)
        use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
        check_constraint = st.checkbox("确保同一处理在不同区组间不出现在同一位置", value=True)
    
    pn_cfg = plot_number_settings(key_prefix="rcbd")
    
    if st.button("生成设计方案"):
        # 基于时钟生成随机种子
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 使用约束随机化生成
        df_design = generate_rcbd_with_constraint(treatment_list, n_blocks, seed, check_constraint)
        
        # 根据小区号设置重新计算
        _pn_col = []
        for _, row in df_design.iterrows():
            _block_num = int(row['区组'].replace('区组', ''))
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=_block_num, treat_idx=int(row['区内位置'])))
        df_design['小区号'] = _pn_col
        
        st.success(f"✅ 已生成 {len(treatment_list)} 处理 × {n_blocks} 区组 = {len(df_design)} 个小区")
        
        # 显示设计表（使用带样式的表格展示各区组内随机排列）
        st.markdown("#### 📋 区组内随机排列")
        show_block_layout_table(df_design, treatment_list, n_blocks)
        
        # 显示约束检查结果
        if check_constraint:
            st.markdown("#### 📊 区组间位置约束检查")
            show_block_constraint_check(df_design, treatment_list, n_blocks)
        
        # 下载
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "RCBD设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def lsd_design():
    """拉丁方设计"""
    st.markdown("### 🔲 拉丁方设计 (LSD)")
    
    st.info("""
    **拉丁方设计**可同时控制行和列两个方向的环境变异。
    
    **适用场景**：行向和列向都存在环境梯度（双向肥力差异）。
    
    **特点**：处理数 = 行数 = 列数，每个处理在每行每列恰好出现一次。
    
    **限制**：处理数不能太多（一般≤10），否则试验规模过大。
    
    **输入**：处理名称列表（处理数 = 行列数）。
    
    **输出**：拉丁方排列矩阵、田间排列可视化图。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        treatments = create_text_input_with_file_import(
            "处理名称（每行一个）", 
            "N0\nN1\nN2\nN3\nN4", 
            height=150,
            key="lsd_treatments"
        )
        treatment_list = [t.strip() for t in treatments.split('\n') if t.strip()]
        n = len(treatment_list)
    
    with col2:
        use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
        st.info(f"将生成 {n}×{n} = {n*n} 个小区")
    
    pn_cfg = plot_number_settings(key_prefix="lsd")
    
    if st.button("生成设计方案"):
        # 基于时钟生成随机种子
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 生成基础拉丁方
        latin_square = [[(i + j) % n for j in range(n)] for i in range(n)]
        
        # 随机化行和列
        row_perm = np.random.permutation(n)
        col_perm = np.random.permutation(n)
        
        randomized = [[latin_square[row_perm[i]][col_perm[j]] for j in range(n)] for i in range(n)]
        
        # 转换为DataFrame
        plots = []
        for i in range(n):
            for j in range(n):
                plots.append({
                    '行': i + 1,
                    '列': j + 1,
                    '处理': treatment_list[randomized[i][j]],
                    '小区号': len(plots) + 1
                })
        
        df_design = pd.DataFrame(plots)
        
        # 根据小区号设置重新计算
        _pn_col = []
        for _, row in df_design.iterrows():
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=int(row['行']), treat_idx=int(row['列'])))
        df_design['小区号'] = _pn_col
        
        st.success(f"✅ 已生成 {n}×{n} 拉丁方设计")
        
        # 显示拉丁方
        st.markdown("#### 📋 拉丁方排列")
        pivot_df = df_design.pivot(index='行', columns='列', values='处理')
        st.dataframe(pivot_df, use_container_width=True)
        
        # 可视化
        fig = visualize_lsd_layout(df_design, n)
        st.plotly_chart(fig, use_container_width=True)
        
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "LSD设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def split_plot_design():
    """裂区设计"""
    st.markdown("### ✂️ 裂区设计 (Split Plot)")
    
    st.info("""
    **裂区设计**用于一个因素需要大面积、另一个因素小面积的情况。
    
    **适用场景**：如耕作方式（主区，大面积作业）× 品种（副区，小区操作）。
    
    **结构**：
    - **主区**：施加主处理（因素A），面积大
    - **副区**：主区内再细分，施加副处理（因素B）
    - **区组**：每个区组包含所有主处理×副处理组合
    
    **注意**：主区和副区的误差项不同，副区比较精度通常更高。
    
    **输入**：主处理列表 + 副处理列表 + 区组数。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        main_plots = create_text_input_with_file_import(
            "主处理（每行一个）", 
            "耕作方式A\n耕作方式B", 
            height=100,
            key="split_main"
        )
        main_list = [t.strip() for t in main_plots.split('\n') if t.strip()]
    
    with col2:
        sub_plots = create_text_input_with_file_import(
            "副处理（每行一个）", 
            "品种X\n品种Y\n品种Z", 
            height=100,
            key="split_sub"
        )
        sub_list = [t.strip() for t in sub_plots.split('\n') if t.strip()]
    
    n_reps = st.number_input("重复次数", min_value=2, max_value=10, value=3)
    use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
    if not use_random_seed:
        seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    check_constraint = st.checkbox("确保同一主处理在不同重复间不出现在同一位置", value=True)
    
    pn_cfg = plot_number_settings(key_prefix="split")
    
    if st.button("生成设计方案"):
        # 基于时钟生成随机种子
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 使用约束随机化生成
        df_design = generate_split_plot_with_constraint(main_list, sub_list, n_reps, seed, check_constraint)
        
        # 根据小区号设置重新计算（副处理位置作为区内序号）
        _pn_col = []
        _sub_idx = 0
        _cur_rep = None
        for _, row in df_design.iterrows():
            _rep_num = int(row['重复'].replace('重复', ''))
            if _rep_num != _cur_rep:
                _cur_rep = _rep_num
                _sub_idx = 0
            _sub_idx += 1
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=_rep_num, treat_idx=_sub_idx))
        df_design['小区号'] = _pn_col
        
        st.success(f"✅ 已生成 {len(main_list)} 主处理 × {len(sub_list)} 副处理 × {n_reps} 重复 = {len(df_design)} 个小区")
        
        st.markdown("#### 📋 裂区设计排列")
        st.dataframe(df_design, use_container_width=True)
        
        # 显示约束检查结果
        if check_constraint:
            st.markdown("#### 📊 主处理位置约束检查")
            show_split_plot_constraint_check(df_design, main_list, n_reps)
        
        # 下载
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "裂区设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def strip_plot_design():
    """条区设计"""
    st.markdown("### 📊 条区设计 (Strip Plot)")
    
    st.info("""
    **条区设计**用于两个因素都需要大面积实施的情况。
    
    **适用场景**：如灌溉方式（横向条带）× 施肥量（纵向条带），两者都需大面积作业。
    
    **结构**：每个区组内，因素A的各水平排成横向条带，因素B的各水平排成纵向条带，交叉形成小区。
    
    **与裂区的区别**：
    - 裂区：一个因素大面积、一个小面积（层次关系）
    - 条区：两个因素都大面积（交叉关系）
    
    **输入**：因素A水平列表 + 因素B水平列表 + 区组数。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        factor_a = create_text_input_with_file_import(
            "因素A水平（每行一个）", 
            "施肥量高\n施肥量中\n施肥量低", 
            height=100,
            key="strip_factor_a"
        )
        a_list = [t.strip() for t in factor_a.split('\n') if t.strip()]
    
    with col2:
        factor_b = create_text_input_with_file_import(
            "因素B水平（每行一个）", 
            "灌溉多\n灌溉中\n灌溉少", 
            height=100,
            key="strip_factor_b"
        )
        b_list = [t.strip() for t in factor_b.split('\n') if t.strip()]
    
    n_reps = st.number_input("重复次数", min_value=2, max_value=10, value=3)
    use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
    if not use_random_seed:
        seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    check_constraint = st.checkbox("确保同一水平在不同重复间不出现在同一位置", value=True)
    
    pn_cfg = plot_number_settings(key_prefix="strip")
    
    if st.button("生成设计方案"):
        # 基于时钟生成随机种子
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 使用约束随机化生成
        df_design = generate_strip_plot_with_constraint(a_list, b_list, n_reps, seed, check_constraint)
        
        # 根据小区号设置重新计算
        _pn_col = []
        _pos_idx = 0
        _cur_rep = None
        for _, row in df_design.iterrows():
            _rep_num = int(row['重复'].replace('重复', ''))
            if _rep_num != _cur_rep:
                _cur_rep = _rep_num
                _pos_idx = 0
            _pos_idx += 1
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=_rep_num, treat_idx=_pos_idx))
        df_design['小区号'] = _pn_col
        
        st.success(f"✅ 已生成 {len(a_list)} A水平 × {len(b_list)} B水平 × {n_reps} 重复 = {len(df_design)} 个小区")
        
        st.markdown("#### 📋 条区设计排列")
        st.dataframe(df_design, use_container_width=True)
        
        # 显示约束检查结果
        if check_constraint:
            st.markdown("#### 📊 因素位置约束检查")
            show_strip_plot_constraint_check(df_design, a_list, b_list, n_reps)
        
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "条区设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def met_design():
    """MET多点试验设计"""
    st.markdown("### 🌍 MET多点试验设计")
    
    st.info("""
    **MET (Multi-Environment Trial) 设计**用于品种/处理在多地点的联合试验方案。
    
    **适用场景**：品种区域试验，需要在多个地点同时评价品种表现。
    
    **结构**：每个地点独立做一个区组设计（RCBD），所有地点使用相同的品种和处理。
    
    **输入**：品种列表 + 地点列表 + 每地点重复数。
    
    **输出**：各地点的随机化排列、田间排列可视化图、试验方案汇总。
    
    **后续分析**：设计完成后可使用"方差分析"页面的 MET 多点联合分析进行数据分析。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        varieties = create_text_input_with_file_import(
            "品种/处理（每行一个）", 
            "品种A\n品种B\n品种C\n品种D\n品种E\n品种F\n品种G\n品种H", 
            height=150,
            key="met_varieties"
        )
        variety_list = [t.strip() for t in varieties.split('\n') if t.strip()]
    
    with col2:
        locations = create_text_input_with_file_import(
            "试验地点（每行一个）", 
            "地点1-北京\n地点2-河南\n地点3-四川\n地点4-广东", 
            height=150,
            key="met_locations"
        )
        location_list = [t.strip() for t in locations.split('\n') if t.strip()]
    
    design_type = st.selectbox("单点设计类型", ["随机区组(RCBD)", "完全随机(CRD)"])
    n_reps = st.number_input("每地点重复次数", min_value=2, max_value=10, value=3)
    use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
    if not use_random_seed:
        seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    check_row_constraint = st.checkbox("确保同一品种不在同一行连续出现", value=True)
    first_rep_not_random = st.checkbox("第一重复不随机（按品种顺序排列）", value=False)
    all_locations_same_order = st.checkbox("所有点的排列顺序一致（所有地点共用一套排列）", value=False)
    
    pn_cfg = plot_number_settings(has_environment=True, key_prefix="met")
    
    if st.button("生成MET设计方案"):
        # 基于时钟生成随机种子
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        all_designs = []
        shared_design_template = None  # 存储共享的排列模板
        
        for loc_idx, loc in enumerate(location_list):
            # 如果所有点排列一致且已有模板，直接使用模板
            if all_locations_same_order and shared_design_template is not None:
                loc_design = shared_design_template.copy()
                loc_design['地点'] = loc
                # 更新小区编号为当前地点
                loc_design['小区编号'] = [f"{str(loc)[:3]}-{row['区组/重复']}-{row['区内位置']}" 
                                          for _, row in loc_design.iterrows()]
            else:
                # 生成新的设计
                if design_type == "随机区组(RCBD)":
                    loc_design = generate_rcbd_for_met(variety_list, n_reps, loc, seed, check_row_constraint, 
                                                        first_rep_not_random)
                else:
                    loc_design = generate_crd_for_met(variety_list, n_reps, loc, seed,
                                                      first_rep_not_random)
                
                # 如果是第一个地点且需要所有点一致，保存为模板
                if all_locations_same_order and shared_design_template is None:
                    shared_design_template = loc_design.copy()
            
            all_designs.append(loc_design)
        
        df_met = pd.concat(all_designs, ignore_index=True)
        
        # 根据小区号设置重新计算
        _pn_col = []
        for _, row in df_met.iterrows():
            _loc_idx = location_list.index(row['地点']) + 1 if row['地点'] in location_list else 1
            _block_str = str(row['区组/重复'])
            _block_num = int(''.join(filter(str.isdigit, _block_str)) or '0')
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=_block_num, treat_idx=int(row['区内位置']), env_idx=_loc_idx))
        df_met['小区编号'] = _pn_col
        
        st.success(f"✅ 已生成 {len(location_list)} 地点 × {len(variety_list)} 品种 × {n_reps} 重复 = {len(df_met)} 个小区")
        
        # 按地点显示
        st.markdown("#### 📋 各地点设计预览")
        for loc in location_list:
            with st.expander(f"📍 {str(loc)}"):
                loc_data = df_met[df_met['地点'] == loc]
                pivot = loc_data.pivot(index='区组/重复', columns='区内位置', values='品种')
                st.dataframe(pivot, use_container_width=True)
        
        # 下载完整方案
        csv = df_met.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载完整MET设计方案 (CSV)", csv, "MET试验设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")

        



def generate_rcbd_for_met(treatments, n_reps, location, seed, check_constraint=True, 
                          first_rep_not_random=False):
    """为MET生成RCBD设计，确保同一品种在不同区组间不出现在同一位置"""
    plots = []
    previous_blocks = []  # 存储之前所有区组的排列
    
    for block in range(1, n_reps + 1):
        block_treatments = treatments.copy()
        
        # 第一重复不随机（按品种顺序排列）
        if block == 1 and first_rep_not_random:
            # 保持原始顺序，不随机
            pass
        else:
            np.random.shuffle(block_treatments)
            
            # 如果检查约束，确保同一品种不在同一位置
            if check_constraint and previous_blocks:
                max_attempts = 1000
                for attempt in range(max_attempts):
                    # 检查与之前所有区组是否有同一位置同一品种
                    has_conflict = False
                    for prev_block in previous_blocks:
                        for i in range(len(treatments)):
                            if block_treatments[i] == prev_block[i]:
                                has_conflict = True
                                break
                        if has_conflict:
                            break
                    
                    if not has_conflict:
                        break
                    np.random.shuffle(block_treatments)
                
                if has_conflict:
                    st.warning(f"⚠️ {str(location)} 区组{block}：无法在1000次尝试内找到满足约束的排列，使用最佳尝试结果")
        
        # 保存当前区组排列
        previous_blocks.append(block_treatments.copy())
        
        for pos, treat in enumerate(block_treatments, 1):
            plots.append({
                '地点': location,
                '区组/重复': f'区组{block}',
                '区内位置': pos,
                '品种': treat,
                '小区编号': f"{str(location)[:3]}-B{block}-{pos}"
            })
    
    return pd.DataFrame(plots)


def generate_crd_for_met(treatments, n_reps, location, seed, 
                         first_rep_not_random=False):
    """为MET生成CRD设计"""
    plots = []
    previous_reps = []  # 存储之前各重复的排列
    
    for rep in range(1, n_reps + 1):
        rep_treatments = treatments.copy()
        
        # 第一重复不随机（按品种顺序排列）
        if rep == 1 and first_rep_not_random:
            # 保持原始顺序，不随机
            pass
        else:
            np.random.shuffle(rep_treatments)
        
        # 保存当前重复排列
        previous_reps.append(rep_treatments.copy())
        
        for pos, treat in enumerate(rep_treatments, 1):
            plots.append({
                '地点': location,
                '区组/重复': f'重复{rep}',
                '区内位置': pos,
                '品种': treat,
                '小区编号': f"{str(location)[:3]}-R{rep}-{pos}"
            })
    
    return pd.DataFrame(plots)


# ========== 约束随机化生成函数 ==========

def generate_crd_with_constraint(treatments, n_reps, seed, check_constraint=True):
    """生成带位置约束的CRD设计"""
    n_treats = len(treatments)
    all_plots = []
    previous_reps = []  # 存储之前各重复的排列
    
    for rep in range(1, n_reps + 1):
        # 生成当前重复的随机排列
        rep_treatments = treatments.copy()
        np.random.shuffle(rep_treatments)
        
        # 检查约束：同一处理不在同一位置
        if check_constraint and previous_reps:
            max_attempts = 1000
            for attempt in range(max_attempts):
                has_conflict = False
                for prev_rep in previous_reps:
                    for i in range(n_treats):
                        if rep_treatments[i] == prev_rep[i]:
                            has_conflict = True
                            break
                    if has_conflict:
                        break
                
                if not has_conflict:
                    break
                np.random.shuffle(rep_treatments)
            
            if has_conflict:
                st.warning(f"⚠️ 重复{rep}：无法在1000次尝试内找到满足约束的排列，使用最佳尝试结果")
        
        previous_reps.append(rep_treatments.copy())
        
        # 记录当前重复的排列
        for pos, treat in enumerate(rep_treatments, 1):
            all_plots.append({
                '处理': treat,
                '重复': rep,
                '位置': pos,
                '小区号': len(all_plots) + 1,
                '排列序号': len(all_plots) + 1
            })
    
    df = pd.DataFrame(all_plots)
    return df


def generate_rcbd_with_constraint(treatments, n_blocks, seed, check_constraint=True):
    """生成带位置约束的RCBD设计"""
    all_plots = []
    previous_blocks = []  # 存储之前所有区组的排列
    
    for block in range(1, n_blocks + 1):
        block_treatments = treatments.copy()
        np.random.shuffle(block_treatments)
        
        # 检查约束：同一处理不在同一位置
        if check_constraint and previous_blocks:
            max_attempts = 1000
            for attempt in range(max_attempts):
                has_conflict = False
                for prev_block in previous_blocks:
                    for i in range(len(treatments)):
                        if block_treatments[i] == prev_block[i]:
                            has_conflict = True
                            break
                    if has_conflict:
                        break
                
                if not has_conflict:
                    break
                np.random.shuffle(block_treatments)
            
            if has_conflict:
                st.warning(f"⚠️ 区组{block}：无法在1000次尝试内找到满足约束的排列，使用最佳尝试结果")
        
        previous_blocks.append(block_treatments.copy())
        
        for pos, treat in enumerate(block_treatments, 1):
            all_plots.append({
                '区组': f'区组{block}',
                '区内位置': pos,
                '处理': treat,
                '小区号': len(all_plots) + 1
            })
    
    return pd.DataFrame(all_plots)


def generate_split_plot_with_constraint(main_list, sub_list, n_reps, seed, check_constraint=True):
    """生成带位置约束的裂区设计"""
    plots = []
    previous_main = []  # 存储之前各重复的主处理排列
    
    for rep in range(1, n_reps + 1):
        # 主处理随机化
        main_random = main_list.copy()
        np.random.shuffle(main_random)
        
        # 检查约束：同一主处理不在同一位置
        if check_constraint and previous_main:
            max_attempts = 1000
            for attempt in range(max_attempts):
                has_conflict = False
                for prev_rep in previous_main:
                    for i in range(len(main_list)):
                        if main_random[i] == prev_rep[i]:
                            has_conflict = True
                            break
                    if has_conflict:
                        break
                
                if not has_conflict:
                    break
                np.random.shuffle(main_random)
            
            if has_conflict:
                st.warning(f"⚠️ 重复{rep}：无法在1000次尝试内找到满足约束的排列，使用最佳尝试结果")
        
        previous_main.append(main_random.copy())
        
        for main_pos, main in enumerate(main_random, 1):
            # 副处理随机化（每个主区内独立随机）
            sub_random = sub_list.copy()
            np.random.shuffle(sub_random)
            
            for sub_pos, sub in enumerate(sub_random, 1):
                plots.append({
                    '重复': f'重复{rep}',
                    '主区位置': main_pos,
                    '主处理': main,
                    '副处理': sub,
                    '小区号': len(plots) + 1
                })
    
    return pd.DataFrame(plots)


def generate_strip_plot_with_constraint(a_list, b_list, n_reps, seed, check_constraint=True):
    """生成带位置约束的条区设计"""
    plots = []
    previous_a = []  # 存储之前各重复的A因素排列
    previous_b = []  # 存储之前各重复的B因素排列
    
    for rep in range(1, n_reps + 1):
        a_random = a_list.copy()
        b_random = b_list.copy()
        np.random.shuffle(a_random)
        np.random.shuffle(b_random)
        
        # 检查约束：同一水平不在同一位置
        if check_constraint and previous_a:
            max_attempts = 1000
            for attempt in range(max_attempts):
                has_conflict = False
                # 检查A因素
                for prev_a in previous_a:
                    for i in range(len(a_list)):
                        if a_random[i] == prev_a[i]:
                            has_conflict = True
                            break
                    if has_conflict:
                        break
                # 检查B因素
                if not has_conflict:
                    for prev_b in previous_b:
                        for i in range(len(b_list)):
                            if b_random[i] == prev_b[i]:
                                has_conflict = True
                                break
                        if has_conflict:
                            break
                
                if not has_conflict:
                    break
                np.random.shuffle(a_random)
                np.random.shuffle(b_random)
            
            if has_conflict:
                st.warning(f"⚠️ 重复{rep}：无法在1000次尝试内找到满足约束的排列，使用最佳尝试结果")
        
        previous_a.append(a_random.copy())
        previous_b.append(b_random.copy())
        
        for i, a in enumerate(a_random):
            for j, b in enumerate(b_random):
                plots.append({
                    '重复': f'重复{rep}',
                    'A方向位置': i + 1,
                    'B方向位置': j + 1,
                    '因素A': a,
                    '因素B': b,
                    '组合': f"{a}-{b}",
                    '小区号': len(plots) + 1
                })
    
    return pd.DataFrame(plots)


# ========== 约束检查结果展示函数 ==========

def show_replicate_constraint_check(df, treatments, n_reps):
    """显示CRD各重复间的位置约束检查结果"""
    # 创建位置对比表
    pivot_data = df.pivot(index='位置', columns='重复', values='处理')
    
    # 标记冲突位置
    conflict_info = []
    for pos in pivot_data.index:
        values = pivot_data.loc[pos].values
        unique_values = set(values)
        if len(unique_values) < len(values):
            duplicates = [item for item in unique_values if list(values).count(item) > 1]
            conflict_info.append(f"位置{pos}: {', '.join(duplicates)}")
    
    if conflict_info:
        st.warning("⚠️ 发现以下位置冲突（同一处理出现在同一位置）：\n" + "\n".join(conflict_info))
    else:
        st.success("✅ 所有位置约束检查通过！同一处理在不同重复间不在同一位置。")
    
    st.dataframe(pivot_data, use_container_width=True)


def show_block_layout_table(df, treatments, n_blocks):
    """显示RCBD各区组内随机排列的样式表格"""
    # 创建透视表
    pivot_data = df.pivot(index='区内位置', columns='区组', values='处理')
    
    # 为每个处理分配颜色
    colors = px.colors.qualitative.Set3[:len(treatments)]
    color_map = {t: colors[i % len(colors)] for i, t in enumerate(treatments)}
    
    # 创建样式化的DataFrame
    def color_cells(val):
        """为单元格添加背景色"""
        color = color_map.get(val, '#FFFFFF')
        return f'background-color: {color}; text-align: center; font-weight: bold;'
    
    # 应用样式
    styled_df = pivot_data.style.map(color_cells)
    
    st.dataframe(styled_df, use_container_width=True)


def show_block_constraint_check(df, treatments, n_blocks):
    """显示RCBD各区组间的位置约束检查结果"""
    # 创建位置对比表
    pivot_data = df.pivot(index='区内位置', columns='区组', values='处理')
    
    # 标记冲突位置
    conflict_info = []
    for pos in pivot_data.index:
        values = pivot_data.loc[pos].values
        unique_values = set(values)
        if len(unique_values) < len(values):
            duplicates = [item for item in unique_values if list(values).count(item) > 1]
            conflict_info.append(f"位置{pos}: {', '.join(duplicates)}")
    
    if conflict_info:
        st.warning("⚠️ 发现以下位置冲突（同一处理出现在同一位置）：\n" + "\n".join(conflict_info))
    else:
        st.success("✅ 所有位置约束检查通过！同一处理在不同区组间不在同一位置。")
    
    st.dataframe(pivot_data, use_container_width=True)


def show_split_plot_constraint_check(df, main_list, n_reps):
    """显示裂区设计主处理位置约束检查结果"""
    # 创建主处理位置对比表
    pivot_data = df.pivot_table(index='主区位置', columns='重复', values='主处理', aggfunc='first')
    
    # 标记冲突位置
    conflict_info = []
    for pos in pivot_data.index:
        values = pivot_data.loc[pos].values
        unique_values = set(values)
        if len(unique_values) < len(values):
            duplicates = [item for item in unique_values if list(values).count(item) > 1]
            conflict_info.append(f"主区位置{pos}: {', '.join(duplicates)}")
    
    if conflict_info:
        st.warning("⚠️ 发现以下主处理位置冲突：\n" + "\n".join(conflict_info))
    else:
        st.success("✅ 主处理位置约束检查通过！同一主处理在不同重复间不在同一位置。")
    
    st.dataframe(pivot_data, use_container_width=True)


def show_strip_plot_constraint_check(df, a_list, b_list, n_reps):
    """显示条区设计位置约束检查结果"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**因素A位置检查：**")
        pivot_a = df.pivot_table(index='A方向位置', columns='重复', values='因素A', aggfunc='first')
        
        conflict_a = []
        for pos in pivot_a.index:
            values = pivot_a.loc[pos].values
            unique_values = set(values)
            if len(unique_values) < len(values):
                duplicates = [item for item in unique_values if list(values).count(item) > 1]
                conflict_a.append(f"A位置{pos}: {', '.join(duplicates)}")
        
        if conflict_a:
            st.warning("⚠️ 冲突：\n" + "\n".join(conflict_a))
        else:
            st.success("✅ 通过")
        st.dataframe(pivot_a, use_container_width=True)
    
    with col2:
        st.markdown("**因素B位置检查：**")
        pivot_b = df.pivot_table(index='B方向位置', columns='重复', values='因素B', aggfunc='first')
        
        conflict_b = []
        for pos in pivot_b.index:
            values = pivot_b.loc[pos].values
            unique_values = set(values)
            if len(unique_values) < len(values):
                duplicates = [item for item in unique_values if list(values).count(item) > 1]
                conflict_b.append(f"B位置{pos}: {', '.join(duplicates)}")
        
        if conflict_b:
            st.warning("⚠️ 冲突：\n" + "\n".join(conflict_b))
        else:
            st.success("✅ 通过")
        st.dataframe(pivot_b, use_container_width=True)


# ========== 可视化函数 ==========

def visualize_field_layout(df, title):
    """可视化田间布局"""
    n = len(df)
    n_cols = int(np.ceil(np.sqrt(n)))
    n_rows = int(np.ceil(n / n_cols))
    
    # 创建网格
    grid = np.empty((n_rows, n_cols), dtype=object)
    grid[:] = ''
    
    for idx, row in df.iterrows():
        r = idx // n_cols
        c = idx % n_cols
        grid[r, c] = row['处理']
    
    # 创建数值矩阵用于颜色映射
    z_values = [[hash(s) % 100 if s else 0 for s in row] for row in grid]
    # 创建文本矩阵用于显示
    text_values = [[str(s) if s else '' for s in row] for row in grid]
    
    # 使用 go.Heatmap 创建带文本标注的热力图
    fig = go.Figure(data=go.Heatmap(
        z=z_values,
        text=text_values,
        texttemplate="%{text}",
        colorscale='Viridis',
        showscale=False
    ))
    fig.update_layout(
        title=title,
        height=400,
        xaxis=dict(showticklabels=False),
        yaxis=dict(showticklabels=False, autorange='reversed')
    )
    return fig


def visualize_rcbd_layout(df, treatments):
    """可视化RCBD布局"""
    blocks = df['区组'].unique()
    n_blocks = len(blocks)
    n_treats = len(treatments)
    
    fig = make_subplots(rows=1, cols=n_blocks,
                       subplot_titles=[f"{b}" for b in blocks])
    
    colors = px.colors.qualitative.Set3[:len(treatments)]
    color_map = {t: colors[i % len(colors)] for i, t in enumerate(treatments)}
    
    for idx, block in enumerate(blocks):
        block_data = df[df['区组'] == block]
        
        for _, row in block_data.iterrows():
            fig.add_trace(
                go.Scatter(
                    x=[row['区内位置']],
                    y=[1],
                    mode='markers+text',
                    marker=dict(size=50, color=color_map[row['处理']]),
                    text=row['处理'],
                    textposition='middle center',
                    name=row['处理'],
                    showlegend=(idx == 0)
                ),
                row=1, col=idx + 1
            )
        
        fig.update_xaxes(title_text="区内位置", row=1, col=idx + 1)
        fig.update_yaxes(visible=False, row=1, col=idx + 1)
    
    fig.update_layout(height=300, title_text="RCBD设计 - 各区组内随机排列")
    return fig


def visualize_lsd_layout(df, n):
    """可视化拉丁方布局"""
    pivot = df.pivot(index='行', columns='列', values='处理')
    
    # 为每个处理分配颜色
    treatments = df['处理'].unique()
    colors = px.colors.qualitative.Set3[:len(treatments)]
    
    fig = go.Figure()
    
    for i, treat in enumerate(treatments):
        treat_data = df[df['处理'] == treat]
        fig.add_trace(go.Scatter(
            x=treat_data['列'],
            y=treat_data['行'],
            mode='markers+text',
            marker=dict(size=60, color=colors[i]),
            text=treat,
            textposition='middle center',
            name=treat
        ))
    
    fig.update_layout(
        title=f"{n}×{n} 拉丁方设计",
        xaxis=dict(title='列', tickmode='linear', tick0=1, dtick=1),
        yaxis=dict(title='行', tickmode='linear', tick0=1, dtick=1, autorange='reversed'),
        height=500,
        showlegend=True
    )
    
    return fig


def visualize_met_layout(df, varieties, locations):
    """可视化MET布局概览"""
    # 统计每个地点的品种分布
    summary = df.groupby(['地点', '品种']).size().reset_index(name='重复数')
    
    pivot = summary.pivot(index='品种', columns='地点', values='重复数').fillna(0)
    
    fig = px.imshow(pivot,
                    text_auto='.0f',
                    aspect='auto',
                    color_continuous_scale='Blues',
                    title='MET试验设计 - 各地点品种重复数')
    
    fig.update_layout(height=400)
    return fig


def visualize_field_map(df, location):
    """生成特定地点的田间种植图"""
    blocks = df['区组/重复'].unique()
    
    fig = make_subplots(rows=len(blocks), cols=1,
                       subplot_titles=[f"{b}" for b in blocks],
                       vertical_spacing=0.1)
    
    varieties = df['品种'].unique()
    colors = px.colors.qualitative.Set3[:len(varieties)]
    color_map = {v: colors[i % len(colors)] for i, v in enumerate(varieties)}
    
    for idx, block in enumerate(blocks):
        block_data = df[df['区组/重复'] == block].sort_values('区内位置')
        
        for _, row in block_data.iterrows():
            fig.add_trace(
                go.Scatter(
                    x=[row['区内位置']],
                    y=[1],
                    mode='markers+text',
                    marker=dict(size=40, color=color_map[row['品种']]),
                    text=row['品种'],
                    textposition='middle center',
                    name=row['品种'],
                    showlegend=(idx == 0)
                ),
                row=idx + 1, col=1
            )
        
        fig.update_xaxes(title_text="位置", row=idx + 1, col=1)
        fig.update_yaxes(visible=False, row=idx + 1, col=1)
    
    fig.update_layout(height=100 * len(blocks) + 100,
                     title_text=f"{str(location)} - 田间种植图")
    return fig


# ========== Alpha设计 (Alpha Lattice) ==========

def alpha_lattice_design():
    """Alpha不完全区组设计"""
    st.markdown("### 🧬 Alpha设计 (Alpha Lattice)")
    
    st.info("""
    **Alpha设计**是一种不完全区组设计，适合处理数较多（>20）的品种试验。
    - 每个完整区组分为 s 个不完全区组
    - 每个不完全区组包含 k 个处理
    - 处理数 v = s × k
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        treatments = create_text_input_with_file_import(
            "处理名称（每行一个）", 
            "品种A\n品种B\n品种C\n品种D\n品种E\n品种F\n品种G\n品种H\n品种I\n品种J\n品种K\n品种L", 
            height=150,
            key="alpha_treatments"
        )
        treatment_list = [t.strip() for t in treatments.split('\n') if t.strip()]
        n_treatments = len(treatment_list)
    
    with col2:
        # 自动计算合适的参数
        st.markdown("**区组参数设置：**")
        # 找出所有合适的 (s, k) 组合使得 s*k = n_treatments
        valid_params = []
        for s in range(2, 21):
            for k in range(2, 21):
                if s * k == n_treatments and s >= 2 and k >= 2:
                    valid_params.append((s, k))
        
        if valid_params:
            st.success(f"处理数 {n_treatments} 的有效参数组合：")
            for s, k in valid_params:
                st.markdown(f"  - s={s} 个不完全区组，k={k} 个处理/区组")
            
            # 选择参数
            param_options = [f"s={s}, k={k}" for s, k in valid_params]
            selected_param = st.selectbox("选择区组参数", param_options)
            s = int(selected_param.split("=")[1].split(",")[0])
            k = int(selected_param.split("k=")[1])
        else:
            st.error(f"处理数 {n_treatments} 无法构造成 s×k 形式，请调整处理数")
            st.markdown("常用处理数：6, 8, 9, 10, 12, 15, 16, 18, 20, 24, 25, 27, 30...")
            return
        
        n_reps = st.number_input("完整区组数（重复次数）", min_value=2, max_value=10, value=3)
        use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    pn_cfg = plot_number_settings(key_prefix="alpha")
    
    if st.button("生成Alpha设计方案"):
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 生成Alpha设计
        df_design = generate_alpha_lattice(treatment_list, s, k, n_reps, seed)
        
        # 根据小区号设置重新计算
        _pn_col = []
        _pos_idx = 0
        _cur_rep = None
        for _, row in df_design.iterrows():
            _rep_num = int(row['完整区组'].replace('区组', ''))
            if _rep_num != _cur_rep:
                _cur_rep = _rep_num
                _pos_idx = 0
            _pos_idx += 1
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=_rep_num, treat_idx=_pos_idx))
        df_design['小区号'] = _pn_col
        
        st.success(f"✅ 已生成 Alpha设计：{len(treatment_list)} 处理 × {n_reps} 完整区组 = {len(df_design)} 个小区")
        st.markdown(f"**参数：** s={s}（每区组不完全区组数）× k={k}（每不完全区组处理数）")
        
        # 显示设计表
        st.markdown("#### 📋 Alpha设计排列")
        show_alpha_lattice_layout(df_design, treatment_list, s, k, n_reps)
        
        # 可视化
        fig = visualize_alpha_lattice(df_design, treatment_list, s, k)
        st.plotly_chart(fig, use_container_width=True)
        
        # 下载
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "Alpha设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def generate_alpha_lattice(treatments, s, k, n_reps, seed):
    """生成Alpha设计
    
    参数:
        treatments: 处理列表
        s: 每个完整区组中的不完全区组数
        k: 每个不完全区组的大小
        n_reps: 完整区组数（重复次数）
        seed: 随机种子
    
    返回:
        DataFrame包含完整设计表
    """
    n_treatments = len(treatments)
    plots = []
    
    # 生成基础设计矩阵（循环设计）
    # 使用参数 p = s, q = k 的 alpha 设计
    base_design = generate_alpha_base(s, k)
    
    for rep in range(1, n_reps + 1):
        rep_treatments = treatments.copy()
        np.random.shuffle(rep_treatments)
        
        for block_group in range(s):  # s个不完全区组
            for pos_in_block in range(k):  # 每个区组k个位置
                treatment_idx = base_design[block_group][pos_in_block]
                if treatment_idx < n_treatments:
                    plots.append({
                        '完整区组': f'区组{rep}',
                        '不完全区组': block_group + 1,
                        '区内位置': pos_in_block + 1,
                        '处理': rep_treatments[treatment_idx],
                        '小区号': len(plots) + 1
                    })
    
    return pd.DataFrame(plots)


def generate_alpha_base(s, k):
    """生成Alpha设计的基础矩阵
    
    使用循环设计原理生成 alpha(0,1) 设计
    """
    base = []
    for i in range(s):
        row = []
        for j in range(k):
            # 循环索引
            val = (i * j) % s
            # 添加偏移量确保平衡
            val = (val + j * s // k) % s
            row.append(val * k // s + j % k)
        base.append(row)
    
    # 确保所有处理都被使用，使用更标准的算法
    # 对于 alpha 设计，使用改进的循环生成
    design = []
    treatment_in_block = 0
    
    for i in range(s):
        block = []
        for j in range(k):
            block.append(treatment_in_block)
            treatment_in_block = (treatment_in_block + 1) % (s * k)
        design.append(block)
    
    return design


def show_alpha_lattice_layout(df, treatments, s, k, n_reps):
    """显示Alpha设计布局"""
    colors = px.colors.qualitative.Set3[:len(treatments)]
    color_map = {t: colors[i % len(colors)] for i, t in enumerate(treatments)}
    
    # 按完整区组显示
    for rep in range(1, n_reps + 1):
        rep_data = df[df['完整区组'] == f'区组{rep}']
        
        with st.expander(f"📦 区组 {rep}"):
            # 创建透视表
            pivot = rep_data.pivot(index='不完全区组', columns='区内位置', values='处理')
            st.dataframe(pivot, use_container_width=True)
            
            # 显示不完全区组信息
            st.markdown("**不完全区组详情：**")
            for ib in range(1, s + 1):
                ib_data = rep_data[rep_data['不完全区组'] == ib]
                treatments_in_block = ib_data['处理'].tolist()
                st.markdown(f"  不完全区组{ib}: {', '.join(treatments_in_block)}")


def visualize_alpha_lattice(df, treatments, s, k):
    """可视化Alpha设计"""
    fig = make_subplots(
        rows=len(df['完整区组'].unique()), 
        cols=s,
        subplot_titles=[f'IB{i+1}' for i in range(s) for _ in range(len(df['完整区组'].unique()))],
        vertical_spacing=0.15,
        horizontal_spacing=0.05
    )
    
    colors = px.colors.qualitative.Set3[:len(treatments)]
    color_map = {t: colors[i % len(colors)] for i, t in enumerate(treatments)}
    
    reps = df['完整区组'].unique()
    for rep_idx, rep in enumerate(reps):
        rep_data = df[df['完整区组'] == rep]
        
        for ib in range(1, s + 1):
            ib_data = rep_data[rep_data['不完全区组'] == ib].sort_values('区内位置')
            
            for _, row in ib_data.iterrows():
                fig.add_trace(
                    go.Scatter(
                        x=[row['区内位置']],
                        y=[1],
                        mode='markers+text',
                        marker=dict(size=35, color=color_map[row['处理']]),
                        text=row['处理'],
                        textposition='middle center',
                        name=row['处理'],
                        showlegend=(rep_idx == 0 and ib == 1)
                    ),
                    row=rep_idx + 1, col=ib
                )
            
            fig.update_xaxes(title_text=f"位置", row=rep_idx + 1, col=ib, range=[0.5, k + 0.5])
            fig.update_yaxes(visible=False, row=rep_idx + 1, col=ib)
    
    fig.update_layout(height=120 * len(reps) + 50, showlegend=True,
                     title_text=f"Alpha设计: {len(treatments)}处理, s={s}, k={k}")
    return fig


# ========== Lattice设计 (格子设计) ==========

def lattice_design():
    """Lattice格子设计"""
    st.markdown("### 🔲 Lattice设计 (格子设计)")
    
    st.info("""
    **格子设计**是一种平衡不完全区组设计，处理数必须为完全平方数 (v = k²)。
    - 方形格子：k×k 处理（如9=3×3, 16=4×4, 25=5×5）
    - 立方体格子：k³ 处理
    
    每个处理在每个方向上恰好与所有其他处理相遇一次。
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        treatments = create_text_input_with_file_import(
            "处理名称（每行一个）", 
            "品种A\n品种B\n品种C\n品种D\n品种E\n品种F\n品种G\n品种H\n品种I", 
            height=150,
            key="lattice_treatments"
        )
        treatment_list = [t.strip() for t in treatments.split('\n') if t.strip()]
        n_treatments = len(treatment_list)
    
    with col2:
        # 检查是否为完全平方数
        import math
        k = int(math.sqrt(n_treatments))
        is_square = k * k == n_treatments
        
        if is_square:
            st.success(f"✅ 处理数 {n_treatments} = {k}×{k}，可构建 {k}×{k} 方形格子设计")
            lattice_type = st.selectbox("格子类型", ["方形格子 (k×k)"])
        else:
            st.error(f"❌ 处理数 {n_treatments} 不是完全平方数")
            st.markdown("**请调整处理数为完全平方数：**")
            suggested = [f"{i*i}" for i in range(3, 11)]
            st.markdown(", ".join(suggested))
            return
        
        n_reps = st.number_input("重复次数", min_value=2, max_value=6, value=2)
        use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    pn_cfg = plot_number_settings(key_prefix="lattice")
    
    if st.button("生成Lattice设计方案"):
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 生成Lattice设计
        df_design = generate_lattice_design(treatment_list, k, n_reps, seed)
        
        # 根据小区号设置重新计算
        _pn_col = []
        for _, row in df_design.iterrows():
            _rep_num = int(row['重复'].replace('重复', ''))
            _pos = (int(row['行']) - 1) * k + int(row['列'])
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=_rep_num, treat_idx=_pos))
        df_design['小区号'] = _pn_col
        
        st.success(f"✅ 已生成 {k}×{k} 格子设计：{len(treatment_list)} 处理 × {n_reps} 重复 = {len(df_design)} 个小区")
        
        # 显示设计
        st.markdown("#### 📋 格子设计排列")
        show_lattice_layout(df_design, k, n_reps)
        
        # 可视化
        fig = visualize_lattice_design(df_design, treatment_list, k)
        st.plotly_chart(fig, use_container_width=True)
        
        # 下载
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "Lattice设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def generate_lattice_design(treatments, k, n_reps, seed):
    """生成方形Lattice设计"""
    plots = []
    
    # 生成基础设计（行-列排列）
    # 使用循环设计确保每个处理在每个方向上相遇
    base_design = generate_lattice_base(k)
    
    for rep in range(1, n_reps + 1):
        rep_treatments = treatments.copy()
        np.random.shuffle(rep_treatments)
        
        for row in range(k):
            for col in range(k):
                treatment_idx = base_design[row][col]
                plots.append({
                    '重复': f'重复{rep}',
                    '行': row + 1,
                    '列': col + 1,
                    '处理': rep_treatments[treatment_idx],
                    '小区号': len(plots) + 1
                })
    
    return pd.DataFrame(plots)


def generate_lattice_base(k):
    """生成Lattice设计的基础矩阵"""
    design = []
    for i in range(k):
        row = []
        for j in range(k):
            # 循环排列
            val = (i + j * k) % (k * k)
            val = val % k + (val // k) * k
            row.append(val)
        design.append(row)
    
    # 更标准的方法：行-列循环设计
    base = []
    for i in range(k):
        row = []
        for j in range(k):
            val = (i * k + (i + j) * j) % (k * k)
            row.append(val)
        base.append(row)
    
    return base


def show_lattice_layout(df, k, n_reps):
    """显示Lattice设计布局"""
    for rep in range(1, n_reps + 1):
        with st.expander(f"📦 重复 {rep}"):
            rep_data = df[df['重复'] == f'重复{rep}']
            pivot = rep_data.pivot(index='行', columns='列', values='处理')
            st.dataframe(pivot, use_container_width=True)


def visualize_lattice_design(df, treatments, k):
    """可视化Lattice设计"""
    fig = make_subplots(
        rows=1, cols=len(df['重复'].unique()),
        subplot_titles=[f'重复{r}' for r in range(1, len(df['重复'].unique()) + 1)],
        horizontal_spacing=0.1
    )
    
    colors = px.colors.qualitative.Set3[:len(treatments)]
    color_map = {t: colors[i % len(colors)] for i, t in enumerate(treatments)}
    
    reps = df['重复'].unique()
    for rep_idx, rep in enumerate(reps, 1):
        rep_data = df[df['重复'] == rep]
        
        for _, row in rep_data.iterrows():
            fig.add_trace(
                go.Scatter(
                    x=[row['列']],
                    y=[-row['行']],
                    mode='markers+text',
                    marker=dict(size=50, color=color_map[row['处理']]),
                    text=row['处理'],
                    textposition='middle center',
                    name=row['处理'],
                    showlegend=(rep_idx == 1)
                ),
                row=1, col=rep_idx
            )
        
        fig.update_xaxes(title_text="列", row=1, col=rep_idx, 
                        tickmode='linear', tick0=1, dtick=1, range=[0.5, k + 0.5])
        fig.update_yaxes(title_text="行", row=1, col=rep_idx, 
                        tickmode='linear', tick0=-k, dtick=1, range=[-k - 0.5, -0.5])
    
    fig.update_layout(height=350, showlegend=True, title_text=f"{k}×{k} 格子设计")
    return fig


# ========== 增广设计 (Augmented Design) ==========

def augmented_design():
    """增广设计 - 对照有重复，测试处理无重复"""
    st.markdown("### ➕ 增广设计 (Augmented Design)")
    
    st.info("""
    **增广设计**用于新品种筛选的初级试验：
    - **对照（Check）**：已知的标准品种，有重复
    - **测试处理（Test）**：待筛选的新品种，无重复
    - 对照用于估计区组效应，测试材料无需重复
    
    适合处理数众多（数百甚至上千）但种子量有限的新品种初筛。
    
    **布局方式：**
    - 随机布局：对照和测试在区组内完全随机混合
    - 对角线布局：对照沿对角线均匀分布，测试填充剩余位置
    """)
    
    # 布局方式选择
    layout_type = st.radio(
        "布局方式",
        ["随机布局（对照和测试完全随机混合）", "对角线布局（对照沿对角线均匀分布）"],
        horizontal=True
    )
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**对照品种（每行一个，需有重复）：**")
        checks = create_text_input_with_file_import(
            "对照", 
            "ck1-对照A\nck2-对照B", 
            height=100,
            key="aug_check"
        )
        check_list = [t.strip() for t in checks.split('\n') if t.strip()]
    
    with col2:
        st.markdown("**测试处理（每行一个，无重复）：**")
        tests = create_text_input_with_file_import(
            "测试处理", 
            "T001\nT002\nT003\nT004\nT005\nT006\nT007\nT008", 
            height=150,
            key="aug_test"
        )
        test_list = [t.strip() for t in tests.split('\n') if t.strip()]
    
    if "对角线" in layout_type:
        # 对角线布局设置
        n_checks = len(check_list)
        n_tests = len(test_list)
        n_reps = st.number_input("对照重复次数", min_value=1, max_value=10, value=2,
                                  help="每个对照品种的重复次数。地块不足时系统自动减少重复数，保证所有测试材料正常安排；若有空余小区，用对照轮换填充。")
        total_check = n_checks * n_reps
        
        st.markdown("**地块设置：**")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            n_rows = st.number_input("行数", min_value=2, max_value=50, value=min(8, total_check + n_tests))
        with col_b2:
            n_cols = st.number_input("列数", min_value=2, max_value=50, value=min(10, (total_check + n_tests) // n_rows + 1))
        
        total_plots = n_rows * n_cols
        required_plots = total_check + n_tests
        if total_plots < required_plots:
            # 计算地块能容纳的最大重复数
            max_reps_fit = max(1, (total_plots - n_tests) // n_checks)
            st.warning(f"⚠️ 地块小区数（{total_plots}）不足以容纳完整试验（需 {required_plots} = {n_checks}对照×{n_reps}重复 + {n_tests}测试）。系统将自动减少对照重复数至 {max_reps_fit} 个，保证所有测试材料正常安排；若有空余小区，用对照轮换填充。")
        elif total_plots > required_plots:
            surplus = total_plots - required_plots
            st.info(f"总小区数：{total_plots} | 对照：{total_check} | 测试：{n_tests} | 空余：{surplus} → 将用对照轮换填充")
        else:
            st.info(f"总小区数：{total_plots} | 对照：{total_check} | 测试：{n_tests} | 空余：0")
    else:
        # 随机布局设置
        n_blocks = st.number_input("区组数", min_value=2, max_value=20, value=3)
    
    use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
    if not use_random_seed:
        seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    pn_cfg = plot_number_settings(key_prefix="aug")
    
    if st.button("生成增广设计方案"):
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        
        if "对角线" in layout_type:
            # 对角线布局：优先减少重复数，所有对照参与排列，剩余位置轮换填充
            n_checks_orig = len(check_list)
            required_plots = n_checks_orig * n_reps + len(test_list)
            total_plots = n_rows * n_cols
            effective_n_reps = n_reps
            if total_plots < required_plots:
                effective_n_reps = max(1, (total_plots - len(test_list)) // n_checks_orig)
            df_design, eff_reps, eff_checks = generate_diagonal_check_design(
                check_list, test_list, n_checks_orig, n_reps, n_rows, n_cols, seed,
                effective_n_reps=effective_n_reps
            )
            # 对角线布局：按行列重新计算小区号
            if '小区号' in df_design.columns:
                _pn_col = []
                for _, row in df_design.iterrows():
                    _pos = int(row['行']) * n_cols + int(row['列']) + 1
                    _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=1, treat_idx=_pos))
                df_design['小区号'] = _pn_col
            check_in_df = len(df_design[df_design['类型'].isin(['对照', '对照填充'])])
            test_in_df = len(df_design[df_design['类型'] == '测试'])
            fill_info = f" | 空余 {total_plots - eff_checks * eff_reps - test_in_df} 个小区用对照轮换填充" if total_plots > eff_checks * eff_reps + test_in_df else ""
            if eff_reps < n_reps:
                st.success(f"✅ 对角线增广设计（地块受限，实际 {eff_checks} 对照×{eff_reps}重复）：{len(df_design)} 个小区{fill_info}")
            else:
                st.success(f"✅ 已生成对角线增广设计：{eff_checks} 对照×{eff_reps}重复 + {test_in_df} 测试 = {len(df_design)} 个小区{fill_info}")
            
            # 显示设计
            st.markdown("#### 📋 对角线增广设计排列")
            show_diagonal_check_layout(df_design, n_rows, n_cols)
            
            # 可视化
            fig = visualize_diagonal_check_design(df_design, check_list, n_rows, n_cols)
            st.plotly_chart(fig, use_container_width=True)
            
            # 下载
            csv = df_design.to_csv(index=False).encode('utf-8-sig')
            if can_download():
                st.download_button("📥 下载设计方案 (CSV)", csv, "对角线增广设计方案.csv", "text/csv")
            else:
                st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")

        else:
            # 随机布局
            np.random.seed(seed)
            df_design = generate_augmented_design(check_list, test_list, n_blocks, seed)
            # 随机布局：按区组和位置重新计算小区号
            _pn_col = []
            for _, row in df_design.iterrows():
                _block_num = int(row['区组'].replace('区组', ''))
                _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=_block_num, treat_idx=int(row['区内位置'])))
            df_design['小区号'] = _pn_col
            st.success(f"✅ 已生成随机增广设计：{len(check_list)} 对照×{n_blocks}重复 + {len(test_list)} 测试 = {len(df_design)} 个小区")
            
            # 显示设计
            st.markdown("#### 📋 随机增广设计排列")
            show_augmented_layout(df_design, check_list, test_list, n_blocks)
            
            # 可视化
            fig = visualize_augmented_design(df_design, check_list, test_list)
            st.plotly_chart(fig, use_container_width=True)
            
            # 下载
            csv = df_design.to_csv(index=False).encode('utf-8-sig')
            if can_download():
                st.download_button("📥 下载设计方案 (CSV)", csv, "随机增广设计方案.csv", "text/csv")
            else:
                st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def generate_augmented_design(checks, tests, n_blocks, seed):
    """生成增广设计 - 对照与测试处理在区组内完全随机混合排列"""
    import random

    # 设置随机种子
    random.seed(seed)

    def _shuffle_without_adjacent_checks(treatments, max_attempts=200):
        """
        打乱处理列表，保证对照不相邻。
        策略：反复打乱 + 交换，直到无相邻对照。
        返回：排好序的 treatments 列表（原地不修改原列表）。
        """
        items = treatments[:]
        for _ in range(max_attempts):
            random.shuffle(items)
            # 检查是否有相邻对照
            has_adjacent = False
            for i in range(len(items) - 1):
                if items[i]['is_check'] and items[i + 1]['is_check']:
                    has_adjacent = True
                    break
            if not has_adjacent:
                return items
        # 重排失败则用贪婪交换法强制消除相邻
        random.shuffle(items)
        for _ in range(len(items) * 2):
            has_adjacent = False
            swapped = False
            for i in range(len(items) - 1):
                if items[i]['is_check'] and items[i + 1]['is_check']:
                    # 找最近的非对照项交换
                    left_swap = None
                    right_swap = None
                    for j in range(i - 1, -1, -1):
                        if not items[j]['is_check']:
                            left_swap = j
                            break
                    for j in range(i + 2, len(items)):
                        if not items[j]['is_check']:
                            right_swap = j
                            break
                    swap_j = left_swap if left_swap is not None else right_swap
                    if swap_j is not None:
                        items[i], items[swap_j] = items[swap_j], items[i]
                        swapped = True
                    else:
                        has_adjacent = True
                    break
            if not has_adjacent and not swapped:
                break
        return items

    plots = []
    n_checks = len(checks)
    n_tests = len(tests)

    # 每个区组的大小：所有对照重复 + 部分测试处理（轮换）
    tests_per_block = int(np.ceil(n_tests / n_blocks))

    for block in range(1, n_blocks + 1):
        block_treatments = []

        # 添加对照（每个对照出现一次）
        for check in checks:
            block_treatments.append({'name': check, 'is_check': True})

        # 添加测试处理（每个区组不同）
        start_idx = (block - 1) * tests_per_block
        end_idx = min(start_idx + tests_per_block, n_tests)
        for test in tests[start_idx:end_idx]:
            block_treatments.append({'name': test, 'is_check': False})

        # 对照与测试处理一起随机打乱，且对照不相邻
        block_treatments = _shuffle_without_adjacent_checks(block_treatments)

        for pos, treat in enumerate(block_treatments, 1):
            plots.append({
                '区组': f'区组{block}',
                '区内位置': pos,
                '处理': treat['name'],
                '类型': '对照' if treat['is_check'] else '测试',
                '小区号': len(plots) + 1
            })

    return pd.DataFrame(plots)


def show_augmented_layout(df, checks, tests, n_blocks):
    """显示增广设计布局 - 每个重复一个列表，对照和测试按位置顺序排列"""
    for block in range(1, n_blocks + 1):
        with st.expander(f"📦 区组 {block}"):
            block_data = df[df['区组'] == f'区组{block}'].sort_values('区内位置')
            
            # 按区内位置顺序显示所有处理
            st.markdown("**区内排列顺序：**")
            display_df = block_data[['区内位置', '处理', '类型']].copy()
            st.dataframe(display_df, use_container_width=True)


def visualize_augmented_design(df, checks, tests):
    """可视化增广设计"""
    fig = make_subplots(
        rows=1, cols=len(df['区组'].unique()),
        subplot_titles=[f'区组{b}' for b in range(1, len(df['区组'].unique()) + 1)],
        horizontal_spacing=0.08
    )
    
    # 对照和测试用不同颜色
    check_colors = px.colors.qualitative.Set1[:len(checks)]
    test_color = '#808080'  # 灰色
    
    blocks = df['区组'].unique()
    for block_idx, block in enumerate(blocks, 1):
        block_data = df[df['区组'] == block].sort_values('区内位置')
        
        for _, row in block_data.iterrows():
            if row['类型'] == '对照':
                color = check_colors[checks.index(row['处理']) % len(check_colors)]
            else:
                color = test_color
            
            fig.add_trace(
                go.Scatter(
                    x=[row['区内位置']],
                    y=[1],
                    mode='markers+text',
                    marker=dict(size=40, color=color),
                    text=row['处理'][:8],  # 截断显示
                    textposition='middle center',
                    name=row['处理'],
                    showlegend=(block_idx == 1)
                ),
                row=1, col=block_idx
            )
        
        fig.update_xaxes(title_text="位置", row=1, col=block_idx)
        fig.update_yaxes(visible=False, row=1, col=block_idx)
    
    fig.update_layout(height=300, showlegend=True, 
                     title_text=f"增广设计: {len(checks)}对照(彩色) + {len(tests)}测试(灰色)")
    return fig


# ========== 对角线设计 (Diagonal Design) ==========

def diagonal_design():
    """对角线设计"""
    st.markdown("### 📐 对角线设计 (Diagonal Design)")
    
    st.info("""
    **对角线设计**是品种初级筛选中常用的田间排列方式。
    
    **两种模式**：
    - **普通对角线**：处理沿对角线方向依次排列，适合纯筛选目的
    - **对照对角线**：对照品种均匀分布在田块的对角线位置，处理随机插入其间
    
    **适用场景**：品种初级鉴定试验、处理数较多的初筛试验。
    
    **输入**：处理列表（对照对角线需额外提供对照品种）+ 行列数。
    
    **输出**：田间排列可视化图、各重复排列结果。
    """)
    
    design_type = st.selectbox(
        "设计模式", 
        ["普通对角线", "对照对角线（对照均匀分布）"]
    )
    
    if design_type == "普通对角线":
        _diagonal_basic_design()
    else:
        _diagonal_check_design()


def _diagonal_basic_design():
    """普通对角线设计"""
    st.info("""
    **普通对角线设计**用于控制田间单向或双向土壤梯度：
    - 所有处理沿对角线方向排列
    - 每个处理都能在不同肥力水平的地块上出现
    - 有效抵消土壤差异带来的系统误差
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        treatments = create_text_input_with_file_import(
            "处理名称（每行一个）", 
            "品种A\n品种B\n品种C\n品种D", 
            height=150,
            key="diag_treatments"
        )
        treatment_list = [t.strip() for t in treatments.split('\n') if t.strip()]
        n = len(treatment_list)
    
    with col2:
        layout_type = st.selectbox("布局类型", ["方形对角线", "矩形对角线"])
        
        # 根据品种数量动态设置最大值（至少为品种数，确保能放下所有品种）
        max_rows = max(n, 20)
        
        if layout_type == "方形对角线":
            n_rows = st.number_input("行数", min_value=2, max_value=max_rows, value=n)
            n_cols = n_rows  # 方形时行列相等
            st.success(f"将生成 {n_rows}×{n_cols} = {n_rows*n_cols} 个小区")
        else:
            max_cols = max(n, 20)
            n_rows = st.number_input("行数", min_value=2, max_value=max_rows, value=min(4, n))
            n_cols = st.number_input("列数", min_value=2, max_value=max_cols, value=n)
            st.success(f"将生成 {n_rows}×{n_cols} = {n_rows*n_cols} 个小区")
        
        use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    pn_cfg = plot_number_settings(key_prefix="diag")
    
    if st.button("生成对角线设计方案"):
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        np.random.seed(seed)
        
        # 生成对角线设计
        df_design = generate_diagonal_design(treatment_list, n_rows, n_cols, seed)
        
        # 按行列重新计算小区号
        _pn_col = []
        for _, row in df_design.iterrows():
            _pos = int(row['行']) * n_cols + int(row['列']) + 1
            _pn_col.append(calculate_plot_number(pn_cfg, rep_idx=1, treat_idx=_pos))
        df_design['小区号'] = _pn_col
        
        st.success(f"✅ 已生成对角线设计：{n_rows}×{n_cols} = {len(df_design)} 个小区")
        
        # 显示设计
        st.markdown("#### 📋 对角线设计排列")
        show_diagonal_layout(df_design, n_rows, n_cols)
        
        # 可视化
        fig = visualize_diagonal_design(df_design, treatment_list, n_rows, n_cols)
        st.plotly_chart(fig, use_container_width=True)
        
        # 下载
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "对角线设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def _diagonal_check_design():
    """对照对角线设计 - 对照沿对角线均匀分布，测试材料填剩余位置"""
    st.info("""
    **对照对角线设计**：
    - 对照品种沿对角线方向均匀排列
    - 测试材料随机填充剩余位置
    - 适合对照品种较少、测试材料较多的筛选试验
    """)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**对照品种（每行一个）：**")
        checks = create_text_input_with_file_import(
            "对照", 
            "ck1\nck2", 
            height=80,
            key="diag_checks"
        )
        check_list = [t.strip() for t in checks.split('\n') if t.strip()]
        
        st.markdown("**测试材料（每行一个）：**")
        tests = create_text_input_with_file_import(
            "测试", 
            "T001\nT002\nT003\nT004\nT005\nT006\nT007\nT008\nT009\nT010\nT011\nT012", 
            height=150,
            key="diag_tests"
        )
        test_list = [t.strip() for t in tests.split('\n') if t.strip()]
    
    with col2:
        n_reps = st.number_input("对照重复次数", min_value=1, max_value=10, value=3, 
                                  help="每个对照品种在对角线上重复出现的次数。地块不足时系统自动减少重复数，保证所有测试材料正常安排；若有空余小区，用对照轮换填充。")
        
        layout_type = st.selectbox("地块形状", ["方形", "矩形"])
        
        n_checks = len(check_list)
        n_tests = len(test_list)
        n_total = n_checks * n_reps + n_tests  # 总小区数
        
        # 估算所需面积
        if layout_type == "方形":
            import math
            size = math.ceil(math.sqrt(n_total))
            max_size = max(size, 20)
            n_rows = st.number_input("行数", min_value=2, max_value=max_size, value=size)
            n_cols = n_rows
        else:
            import math
            size = math.ceil(math.sqrt(n_total))
            max_size = max(size, 20)
            n_rows = st.number_input("行数", min_value=2, max_value=max_size, value=size)
            n_cols = st.number_input("列数", min_value=2, max_value=max_size, value=size)
        
        total_plots_preview = n_rows * n_cols
        if total_plots_preview < n_total:
            # 计算调整后的重复数
            adj_reps = max(1, (total_plots_preview - n_tests) // n_checks)
            adj_capacity = n_checks * adj_reps + n_tests
            st.warning(f"⚠️ 地块小区数（{total_plots_preview}）不足以容纳完整试验 → 系统将自动减少对照重复数至 {adj_reps} 次，保证所有测试材料正常安排；若有空余小区，用对照轮换填充。")
        elif total_plots_preview > n_total:
            st.info(f"总小区数：{total_plots_preview} | 空余：{total_plots_preview - n_total} → 将用对照轮换填充")
        else:
            st.success(f"将生成 {n_rows}×{n_cols} = {n_rows*n_cols} 个小区（恰好容纳）")
        
        use_random_seed = st.checkbox("使用随机种子（基于时钟）", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    pn_cfg_diag = plot_number_settings(key_prefix="diagck")
    
    if st.button("生成对角线设计方案"):
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        
        n_checks_orig = len(check_list)
        n_tests = len(test_list)
        required_plots = n_checks_orig * n_reps + n_tests
        total_plots = n_rows * n_cols
        
        # 优先减少重复数；地块仍不足时减少对照数保底
        effective_n_reps = n_reps
        if total_plots < required_plots:
            effective_n_reps = max(1, (total_plots - n_tests) // n_checks_orig)
        
        # 生成对照对角线设计
        df_design, eff_reps, eff_checks = generate_diagonal_check_design(
            check_list, test_list, n_checks_orig, n_reps, n_rows, n_cols, seed,
            effective_n_reps=effective_n_reps
        )
        
        # 按行列重新计算小区号
        if '小区号' in df_design.columns:
            _pn_col = []
            for _, row in df_design.iterrows():
                _pos = int(row['行']) * n_cols + int(row['列']) + 1
                _pn_col.append(calculate_plot_number(pn_cfg_diag, rep_idx=1, treat_idx=_pos))
            df_design['小区号'] = _pn_col
        
        test_in_df = len(df_design[df_design['类型'] == '测试'])
        fill_info = f" | 空余 {total_plots - eff_checks * eff_reps - test_in_df} 个小区用对照轮换填充" if total_plots > eff_checks * eff_reps + test_in_df else ""
        if eff_reps < n_reps:
            st.success(f"✅ 对照对角线设计（地块受限，实际 {eff_checks} 对照×{eff_reps}重复）：{n_rows}×{n_cols} = {len(df_design)} 个小区{fill_info}")
        else:
            st.success(f"✅ 已生成对照对角线设计：{eff_checks} 对照×{eff_reps}重复 + {test_in_df} 测试 = {len(df_design)} 个小区{fill_info}")
        
        # 显示设计
        st.markdown("#### 📋 对照对角线设计排列")
        show_diagonal_check_layout(df_design, n_rows, n_cols)
        
        # 可视化
        fig = visualize_diagonal_check_design(df_design, check_list, n_rows, n_cols)
        st.plotly_chart(fig, use_container_width=True)
        
        # 下载
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载设计方案 (CSV)", csv, "对照对角线设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def generate_diagonal_design(treatments, n_rows, n_cols, seed):
    """生成对角线设计"""
    plots = []
    n_treatments = len(treatments)
    
    # 创建处理分配矩阵
    # 使用循环分配，每个处理沿对角线重复出现
    treatment_matrix = [[None for _ in range(n_cols)] for _ in range(n_rows)]
    
    # 对角线填充
    for diag in range(n_rows + n_cols - 1):
        diag_positions = []
        for r in range(n_rows):
            c = diag - r
            if 0 <= c < n_cols:
                diag_positions.append((r, c))
        
        # 沿对角线分配处理
        for idx, (r, c) in enumerate(diag_positions):
            treatment_idx = (diag + idx) % n_treatments
            treatment_matrix[r][c] = treatments[treatment_idx]
    
    # 转换为DataFrame（全为对照品种）
    for row in range(n_rows):
        for col in range(n_cols):
            plots.append({
                '行': row + 1,
                '列': col + 1,
                '处理': treatment_matrix[row][col],
                '小区号': row * n_cols + col + 1,
                '类型': '对照'
            })
    
    return pd.DataFrame(plots, columns=['行', '列', '处理', '小区号', '类型'])


def generate_diagonal_check_design(checks, tests, n_checks, n_reps, n_rows, n_cols, seed, effective_n_reps=None):
    """
    生成对照对角线设计（增广设计的对角线布局变体）

    设计原则：
    - 所有对角线（|行-列| = d）都是对照小区的排列位置
    - 对照品种均匀分布在所有对角线上
    - 每个重复的对照品种依次在所有对角线上循环排列
    - 根据位置数量和总对照数规划均匀间隔
    - 地块不足时：先减少重复数，再减少对照数
    """
    import random
    random.seed(seed)

    n_tests    = len(tests)
    total_plots = n_rows * n_cols
    max_diags   = n_rows + n_cols - 1

    # ── 1. 自动计算有效重复数 ────────────────────────────────
    #   规则：测试小区一个也不能少，对照重复数可以减少
    if effective_n_reps is None:
        effective_n_reps = n_reps

    # 从高到低找能容纳所有测试的最大重复数
    found_valid = False
    for r in range(effective_n_reps, 0, -1):
        if n_checks * r + n_tests <= total_plots:
            effective_n_reps = r
            found_valid = True
            break

    # 如果即使 r=1 也不够，减少对照数（而不是减少测试）
    effective_n_checks = n_checks
    if not found_valid:
        # 重新计算：保证所有测试 + 最少1个对照重复
        effective_n_checks = max(1, (total_plots - n_tests) // effective_n_reps)
        # 再次验证：如果还不够，减少重复数
        if n_checks_orig * effective_n_reps + n_tests > total_plots:
            # 减少重复数直到能容纳
            for r in range(effective_n_reps, 0, -1):
                if effective_n_checks * r + n_tests <= total_plots:
                    effective_n_reps = r
                    break

    # ── 2. 构建每条对角线的坐标列表 ─────────────────────────
    diag_positions = [[] for _ in range(max_diags)]
    for r in range(n_rows):
        for c in range(n_cols):
            diag_positions[abs(r - c)].append((r, c))

    # ── 3. 收集所有对角线位置（带对角线编号）────────────────
    all_check_positions = []
    for d, positions in enumerate(diag_positions):
        for (r, c) in positions:
            all_check_positions.append((r, c, d))

    # ── 4. 贪心均匀选取 + 自动减少重复数 ────────────────────
    #   规则：地块不足时，自动减少重复数（保持每品种只出现一次）
    #   约束：严格不相邻（左右上下均不相邻）
    #   贪心均衡：每次选使行/列对照数最均衡的位置
    total_check_slots = effective_n_checks * effective_n_reps

    row_count = [0] * n_rows
    col_count = [0] * n_cols

    # 贪心行/列均衡目标（每行/列尽量均匀）
    checks_per_row = total_check_slots // n_rows
    extra_rows     = total_check_slots % n_rows
    checks_per_col = total_check_slots // n_cols
    extra_cols     = total_check_slots % n_cols
    row_targets = [checks_per_row + (1 if i < extra_rows else 0) for i in range(n_rows)]
    col_targets = [checks_per_col + (1 if i < extra_cols else 0) for i in range(n_cols)]

    sampled_all = []
    remaining   = all_check_positions[:]
    random.shuffle(remaining)

    def select_best(remaining_list, placed, rcount, ccount, rtgt, ctgt):
        """从候选中选 score 最低的位置（贪心均衡）"""
        if not remaining_list:
            return None
        max_r = max(rcount)
        max_c = max(ccount)
        best = None
        best_score = float('inf')
        for p in remaining_list:
            r, c, d = p
            score = max(abs(rcount[r] - max_r), abs(ccount[c] - max_c))
            if score < best_score:
                best_score = score
                best = p
        return best

    # 轮次1：严格非相邻 + 行/列均衡目标（限制总数不超过 total_check_slots）
    while remaining and len(sampled_all) < total_check_slots:
        placed_pos = {(p[0], p[1]) for p in sampled_all}
        candidates = [
            p for p in remaining
            if row_count[p[0]] < row_targets[p[0]]
            and col_count[p[1]] < col_targets[p[1]]
            and (p[0], p[1] - 1) not in placed_pos
            and (p[0], p[1] + 1) not in placed_pos
            and (p[0] - 1, p[1]) not in placed_pos
            and (p[0] + 1, p[1]) not in placed_pos
        ]
        if candidates:
            random.shuffle(candidates)
            best = min(candidates, key=lambda p: max(
                abs(row_count[p[0]] - max(row_count)),
                abs(col_count[p[1]] - max(col_count))
            ))
            sampled_all.append(best)
            remaining.remove(best)
            row_count[best[0]] += 1
            col_count[best[1]] += 1
        else:
            break   # 轮次1用尽，跳轮次2

    # 轮次2：严格非相邻，仅贪心均衡得分（放弃行/列目标，限制总数）
    while remaining and len(sampled_all) < total_check_slots:
        placed_pos = {(p[0], p[1]) for p in sampled_all}
        candidates = [
            p for p in remaining
            if (p[0], p[1] - 1) not in placed_pos
            and (p[0], p[1] + 1) not in placed_pos
            and (p[0] - 1, p[1]) not in placed_pos
            and (p[0] + 1, p[1]) not in placed_pos
        ]
        if not candidates:
            break   # 严格非相邻已无法满足，停止
        random.shuffle(candidates)
        best = min(candidates, key=lambda p: max(
            abs(row_count[p[0]] - max(row_count)),
            abs(col_count[p[1]] - max(col_count))
        ))
        sampled_all.append(best)
        remaining.remove(best)
        row_count[best[0]] += 1
        col_count[best[1]] += 1

    # --- 自动减少重复数 ---
    # 实际放了多少格，就用这个数量重新计算有效重复数
    actual_slots = len(sampled_all)
    for n_r in range(effective_n_reps, 0, -1):
        if effective_n_checks * n_r <= actual_slots:
            effective_n_reps = n_r
            break

    # 重新计算该重复数下实际可用的 slot 数（最多填到 n_checks*n_reps）
    total_check_slots = effective_n_checks * effective_n_reps

    # ── 5. 将采样位置均匀分配给各重复 ──────────────────────
    plot_matrix = [[None for _ in range(n_cols)] for _ in range(n_rows)]
    plot_types  = [[None for _ in range(n_cols)] for _ in range(n_rows)]
    plot_rep    = [[None for _ in range(n_cols)] for _ in range(n_rows)]
    plot_order  = [[None for _ in range(n_cols)] for _ in range(n_rows)]

    used = set()

    for rep_idx in range(effective_n_reps):
        rep_checks = checks[:effective_n_checks].copy()
        random.shuffle(rep_checks)
        ck_idx = 0

        # 该重复要填的位置：按 rep_idx 轮流通取
        for slot in range(rep_idx, len(sampled_all), effective_n_reps):
            r, c, d = sampled_all[slot]
            if (r, c) in used:
                continue

            check_name = rep_checks[ck_idx % len(rep_checks)]
            plot_matrix[r][c] = check_name
            plot_types[r][c]  = '对照'
            plot_rep[r][c]    = rep_idx + 1
            used.add((r, c))
            ck_idx += 1

    # ── 7. 入位顺序：从左上到右下的主对角线（|r-c|=d）均匀排列 ─
    #   从 d=0（主对角线）开始，向右下方遍历各条平行线
    #   步长=2（右移+2，下移+2）；触边则换下一条对角线，从该线左上重新开始
    #   所有对照（含填充）均编号
    all_check_positions_for_order = [
        (r, c) for r in range(n_rows) for c in range(n_cols)
        if plot_types[r][c] in ('对照', '对照填充')
    ]
    ordered = []
    ordered_used = set()
    STEP_N = 2
    # |r-c|=d 的有效 d 上限为 min(n_rows, n_cols)-1
    K = max(3, min(len(all_check_positions_for_order), min(n_rows, n_cols)))

    for d in range(K):
        # 主对角线 |r-c|=d 上所有未排的对照位置
        diag_slots = sorted(
            [(r, c) for (r, c) in all_check_positions_for_order
             if abs(r - c) == d and (r, c) not in ordered_used],
            key=lambda x: (x[0], x[1])   # 先按r升序，再按c升序
        )
        if not diag_slots:
            continue

        # 左上端 = 该线上最小的 r（和对应的 c）
        left_r = min(r for (r, c) in diag_slots)
        if d <= n_rows - 1:
            left_c = 0                           # 与顶边相交，左上端在顶边
        else:
            # 与右边相交，左上端在左边界的最上 cell
            left_c = d - (n_rows - 1)
            left_r = 0
        prev_r = left_r - 1   # 从左上端左侧"前一步"开始
        prev_c = left_c - 1

        while True:
            target_r = prev_r + STEP_N
            target_c = prev_c + STEP_N
            # 找 r>=target_r AND c>=target_c（严格右下方跳步）
            best = None
            for (r, c) in diag_slots:
                if (r, c) in ordered_used:
                    continue
                if r >= target_r and c >= target_c:
                    best = (r, c)
                    break
            # 触边：换下一条对角线
            if best is None:
                break
            ordered.append(best)
            ordered_used.add(best)
            prev_r, prev_c = best

    # 兜底：仍未排的对照按原始顺序追加
    for (r, c) in all_check_positions_for_order:
        if (r, c) not in ordered_used:
            ordered.append((r, c))

    for seq, (r, c) in enumerate(ordered, start=1):
        plot_order[r][c] = seq

    # ── 8. 填测试处理（测试小区优先，一个也不能少）─────────────
    remaining = [(r, c) for r in range(n_rows) for c in range(n_cols)
                 if plot_matrix[r][c] is None]

    # 确保所有测试小区都被安排（算法保证：effective_n_checks * effective_n_reps + n_tests <= total_plots）
    assert len(remaining) >= n_tests, f"地块不足！剩余 {len(remaining)} 格，无法容纳 {n_tests} 个测试小区"

    random.shuffle(remaining)

    test_shuffled = tests.copy()
    random.shuffle(test_shuffled)
    n_test = len(test_shuffled)  # 所有测试小区都会被填入
    for i in range(n_test):
        r, c = remaining[i]
        plot_matrix[r][c] = test_shuffled[i]
        plot_types[r][c]  = '测试'
        plot_rep[r][c]    = 0
        plot_order[r][c]  = 0

    # ── 7. 剩余空位用对照轮换填充 ───────────────────────────
    empty_slots = remaining[n_test:]
    fill_base   = checks[:effective_n_checks]
    # 按 (r+c) 交错避免同行同列聚集
    empty_slots.sort(key=lambda x: x[0] + x[1])
    for i, (r, c) in enumerate(empty_slots):
        ck = fill_base[i % len(fill_base)]
        plot_matrix[r][c] = ck
        plot_types[r][c]  = '对照填充'
        plot_rep[r][c]    = 0
        plot_order[r][c]  = 0

    # ── 8. 构建 DataFrame ────────────────────────────────────
    plots = []
    for r in range(n_rows):
        for c in range(n_cols):
            plots.append({
                '行': r + 1,
                '列': c + 1,
                '处理':   plot_matrix[r][c],
                '类型':   plot_types[r][c],
                '重复':   plot_rep[r][c],
                '顺序':   plot_order[r][c] if plot_order[r][c] is not None else 0,
                '对角线': abs(r - c),
                '小区号': r * n_cols + c + 1,
            })

    return pd.DataFrame(plots), effective_n_reps, effective_n_checks


def show_diagonal_layout(df, n_rows, n_cols):
    """显示对角线设计布局"""
    pivot = df.pivot(index='行', columns='列', values='处理')
    st.dataframe(pivot, use_container_width=True)
    
    # 显示对角线信息
    st.markdown("**设计说明：**")
    st.markdown(f"- 主对角线从左上到右下，共 {min(n_rows, n_cols)} 个对角线")
    st.markdown("- 每个处理沿对角线方向分布，自动穿越不同肥力水平")


def show_diagonal_check_layout(df, n_rows, n_cols):
    """显示对照对角线设计布局（无高亮）"""
    # 合并处理名和顺序号为单列（顺序>0时显示）
    df_disp = df.copy()
    df_disp['显示'] = df_disp.apply(
        lambda r: f"{r['处理']}  #{int(r['顺序'])}" if r['顺序'] and r['顺序'] > 0 else r['处理'],
        axis=1
    )
    pivot = df_disp.pivot(index='行', columns='列', values='显示')
    st.markdown("**处理矩阵（#后数字为入位顺序）：**")
    st.dataframe(pivot, use_container_width=True)
    
    # 统计信息
    check_count = len(df[df['类型'] == '对照'])
    check_fill_count = len(df[df['类型'] == '对照填充'])
    test_count = len(df[df['类型'] == '测试'])
    empty_count = len(df[df['类型'] == '空'])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("对照小区", check_count + check_fill_count)
    with col2:
        st.metric("测试小区", test_count)
    with col3:
        if empty_count > 0:
            st.metric("空小区", empty_count, "⚠️ 测试材料不足")
        elif check_fill_count > 0:
            st.metric("对照填充", check_fill_count, "↔️ 地块有余，对照轮换填充")
        else:
            st.metric("空小区", 0)
    
    # 显示设计说明
    st.markdown("**设计说明：**")
    st.markdown("- 🔵 对照品种沿右下方方向依次入位（#1→#2：行列坐标均增大）")
    if check_fill_count > 0:
        st.markdown(f"- 🔶 地块有余，对照轮换填充（{check_fill_count}个）")
    st.markdown("- ⚪ 测试材料优先填充剩余位置")
    st.markdown("- 对角线索引表示 |行-列| 值，相等表示在同一对角线上")


def visualize_diagonal_design(df, treatments, n_rows, n_cols):
    """可视化对角线设计（高亮所有对角线，对照显示入位顺序）"""
    import seaborn as sns
    import matplotlib.colors as mcolors

    max_diags = n_rows + n_cols - 1
    # 兼容无'重复'列的普通对角线设计
    max_reps = int(df['重复'].max()) if '重复' in df.columns and df['重复'].max() is not pd.NA else 1
    rep_palette = sns.color_palette("tab10", max(10, max_reps + 1))
    diag_palette = sns.color_palette("Blues_r", max_diags)

    # 类型基础色
    type_map = {
        '对照':       '#1976D2',
        '对照填充':   '#90CAF9',
        '测试':       '#E0E0E0',
        '空':         '#F5F5F5',
    }

    fig = go.Figure()

    # ── 1. 所有对角线引导线 ───────────────────────────────────
    for d in range(max_diags):
        dx, dy = [], []
        for r in range(1, n_rows + 1):
            for c in range(1, n_cols + 1):
                if abs(r - c) == d:
                    dx.append(c)
                    dy.append(-r)
        if dx:
            rgb = tuple(int(diag_palette[d][k] * 255) for k in range(3))
            fig.add_trace(go.Scatter(
                x=dx, y=dy, mode='lines',
                line=dict(color=f'rgba({rgb[0]},{rgb[1]},{rgb[2]},0.20)', width=2.5),
                hoverinfo='skip', showlegend=False
            ))

    # ── 2. 对照点：显示顺序编号 ──────────────────────────────
    checks_sub = df[df['类型'] == '对照']
    if not checks_sub.empty:
        has_reps = '重复' in df.columns
        has_order = '顺序' in df.columns
        marker_colors = []
        texts = []
        customdata_list = []
        for _, row in checks_sub.iterrows():
            rep_idx = int(row['重复'] - 1) if has_reps else 0
            rgb = tuple(int(rep_palette[rep_idx % 10][k] * 255) for k in range(3))
            marker_colors.append(f'rgb({rgb[0]},{rgb[1]},{rgb[2]})')
            texts.append(str(int(row['顺序'])) if has_order else str(int(row.name + 1)))
            customdata_list.append([row['处理'], row['重复'] if has_reps else 1])

        fig.add_trace(go.Scatter(
            x=checks_sub['列'], y=-checks_sub['行'],
            mode='markers+text',
            marker=dict(size=78, color=marker_colors, line=dict(width=2.5, color='white')),
            text=texts,
            textposition='middle center',
            textfont=dict(size=9, color='#FFFFFF', family='sans-serif', weight='bold'),
            name='对照（顺序）',
            hovertemplate=(
                "<b>顺序:%{text}</b><br>"
                + "品种:%{customdata[0]}<br>"
                + "重复:%{customdata[1]}<br>"
                + "行:%{y}<br>列:%{x}<extra></extra>"
            ),
            customdata=customdata_list
        ))

    # ── 3. 其他类型（不显示文字）──────────────────────────────
    for tr_type in ['对照填充', '测试', '空']:
        sub = df[df['类型'] == tr_type]
        if sub.empty:
            continue
        hex_c = type_map.get(tr_type, '#888888')
        rgba  = mcolors.to_rgba(hex_c)
        rgb   = f'rgb({int(rgba[0]*255)},{int(rgba[1]*255)},{int(rgba[2]*255)})'
        fig.add_trace(go.Scatter(
            x=sub['列'], y=-sub['行'],
            mode='markers',
            marker=dict(size=72, color=rgb, line=dict(width=1.5, color='#ddd')),
            name=tr_type,
            hovertemplate="<b>%{customdata[0]}</b><br>行:%{y}<br>列:%{x}<extra></extra>",
            customdata=sub[['处理']].values
        ))

    fig.update_layout(
        title=f"对角线设计布局: {n_rows}行×{n_cols}列  |  重复数={max_reps}",
        xaxis=dict(title='列', tickmode='linear', tick0=1, dtick=1,
                   range=[0.5, n_cols + 0.5], fixedrange=True),
        yaxis=dict(title='行', tickmode='linear', tick0=-n_rows, dtick=1,
                   range=[-n_rows - 0.5, -0.5], fixedrange=True),
        height=max(420, n_rows * 52),
        legend=dict(title='类型', orientation='h', yanchor='bottom',
                    y=1.03, xanchor='right', x=1),
        plot_bgcolor='#ffffff', paper_bgcolor='white'
    )

    return fig


def visualize_diagonal_check_design(df, checks, n_rows, n_cols):
    """可视化对照对角线设计（按类型着色：对照蓝色，测试中性，空灰色）"""
    import matplotlib.colors as mcolors
    
    # 按类型着色，对照/填充均蓝色
    style_map = {
        '对照':       ('#1976D2', '#FFFFFF', 80, 3.0),
        '对照填充':   ('#90CAF9', '#0D47A1', 78, 2.5),
        '测试':       ('#FFF8E1', '#795548', 72, 2.0),
        '空':         ('#F5F5F5', '#BDBDBD', 55, 1.0),
    }
    
    fig = go.Figure()
    
    for tr_type in ['对照', '对照填充', '测试', '空']:
        sub = df[df['类型'] == tr_type]
        if sub.empty:
            continue
        
        bg_hex, text_color, size, lw = style_map.get(tr_type, ('#fff', '#333', 60, 1))
        rgba = mcolors.to_rgba(bg_hex)
        rgb_str = f'rgb({int(rgba[0]*255)},{int(rgba[1]*255)},{int(rgba[2]*255)})'
        
        fig.add_trace(go.Scatter(
            x=sub['列'], y=-sub['行'],
            mode='markers+text',
            marker=dict(
                size=size,
                color=rgb_str,
                line=dict(width=lw, color='white' if tr_type != '空' else '#ddd')
            ),
            text=sub['处理'],
            textposition='middle center',
            textfont=dict(size=9, color=text_color, family='sans-serif'),
            name=tr_type,
            hovertemplate="<b>%{text}</b><br>行: %{y}<br>列: %{x}<extra></extra>"
        ))
    
    fig.update_layout(
        title=f"对照对角线设计: {n_rows}行×{n_cols}列",
        xaxis=dict(title='列', tickmode='linear', tick0=1, dtick=1,
                   range=[0.5, n_cols + 0.5], fixedrange=True),
        yaxis=dict(title='行', tickmode='linear', tick0=-n_rows, dtick=1,
                   range=[-n_rows - 0.5, -0.5], fixedrange=True),
        height=max(420, n_rows * 52),
        legend=dict(title='类型', orientation='h', yanchor='bottom',
                    y=1.03, xanchor='right', x=1),
        plot_bgcolor='#ffffff', paper_bgcolor='white'
    )
    
    return fig


# ========== 间比法设计 ==========

def interval_test_design():
    """间比法设计 - 品种初级筛选"""
    st.markdown("### 📈 间比法设计")
    
    st.info("""
    **间比法**是品种初级筛选中最常用的简单设计：
    - 多种类型对照（如CK1、CK2、CK3），按不同间隔重复出现
    - 可设置每个对照的起始小区号和品种名称
    - 适合处理数众多（数十到数百）的新品种初筛
    """)
    
    # 多点设置
    with st.expander("🌍 多点试验设置（可选）", expanded=False):
        locations_input = st.text_area(
            "试验地点列表（每行一个，留空则为单点试验）",
            value="",
            height=80,
            key="interval_locations",
            placeholder="北京\n天津\n石家庄"
        )
        location_list = [l.strip() for l in locations_input.split('\n') if l.strip()]
        all_same_order = st.checkbox("所有地点排列顺序一致", value=False, key="interval_same_order")
    
    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.markdown("**测试处理（每行一个）：**")
        tests = create_text_input_with_file_import(
            "测试处理", 
            "T001\nT002\nT003\nT004\nT005\nT006\nT007\nT008\nT009\nT010\nT011\nT012\nT013\nT014\nT015\nT016\nT017\nT018\nT019\nT020\nT021\nT022\nT023\nT024\nT025\nT026\nT027\nT028\nT029", 
            height=200,
            key="interval_tests"
        )
        test_list = [t.strip() for t in tests.split('\n') if t.strip()]
    
    with col2:
        st.markdown("**对照设置：**")
        
        # CK1设置
        ck1_col1, ck1_col2 = st.columns([0.4, 0.6])
        with ck1_col1:
            use_ck1 = st.checkbox("启用 CK1", value=True)
        with ck1_col2:
            ck1_name = st.text_input("品种名", value="CK1", disabled=not use_ck1,
                                       placeholder="如：丰抗二号", label_visibility="collapsed")
        c1_col1, c1_col2 = st.columns(2)
        ck1_start = c1_col1.number_input("起始位置", min_value=1, value=1,
                                           disabled=not use_ck1, key="ck1_start")
        ck1_interval = c1_col2.number_input("间隔", min_value=3, max_value=50, value=10,
                                            disabled=not use_ck1, key="ck1_intv")
        
        # CK2设置
        ck2_col1, ck2_col2 = st.columns([0.4, 0.6])
        with ck2_col1:
            use_ck2 = st.checkbox("启用 CK2", value=True)
        with ck2_col2:
            ck2_name = st.text_input("品种名", value="CK2", disabled=not use_ck2,
                                       placeholder="如：本地主栽", label_visibility="collapsed")
        c2_col1, c2_col2 = st.columns(2)
        ck2_start = c2_col1.number_input("起始位置", min_value=1, value=1,
                                           disabled=not use_ck2, key="ck2_start")
        ck2_interval = c2_col2.number_input("间隔", min_value=3, max_value=100, value=20,
                                            disabled=not use_ck2, key="ck2_intv")
        
        # CK3设置
        ck3_col1, ck3_col2 = st.columns([0.4, 0.6])
        with ck3_col1:
            use_ck3 = st.checkbox("启用 CK3", value=True)
        with ck3_col2:
            ck3_name = st.text_input("品种名", value="CK3", disabled=not use_ck3,
                                       placeholder="如：区域对照", label_visibility="collapsed")
        c3_col1, c3_col2 = st.columns(2)
        ck3_start = c3_col1.number_input("起始位置", min_value=1, value=1,
                                           disabled=not use_ck3, key="ck3_start")
        ck3_interval = c3_col2.number_input("间隔", min_value=3, max_value=150, value=29,
                                            disabled=not use_ck3, key="ck3_intv")
        
        use_random_seed = st.checkbox("使用随机种子", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    pn_cfg = plot_number_settings(has_environment=len(location_list) > 0, key_prefix="interval")
    
    if st.button("生成间比法设计方案"):
        # 收集启用的对照配置：(品种名, 起始位置, 间隔)
        ck_configs = []
        if use_ck1:
            ck_configs.append((ck1_name.strip() or "CK1", ck1_start, ck1_interval))
        if use_ck2:
            ck_configs.append((ck2_name.strip() or "CK2", ck2_start, ck2_interval))
        if use_ck3:
            ck_configs.append((ck3_name.strip() or "CK3", ck3_start, ck3_interval))
        
        if len(ck_configs) < 1:
            st.warning("⚠️ 请至少启用1种对照")
            return
        
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        
        # 单点 or 多点
        locs = location_list if location_list else [""]
        base_seed = seed
        all_dfs = []
        
        for env_idx, loc in enumerate(locs):
            loc_seed = base_seed if (all_same_order or not location_list) else (base_seed + env_idx * 31)
            df_loc = generate_interval_design_v3(test_list, ck_configs, loc_seed)
            if location_list:
                df_loc.insert(0, '地点', loc)
            # 重新计算小区号
            _pn_col = []
            for pos_i, _ in enumerate(df_loc.iterrows()):
                _pn_col.append(calculate_plot_number(
                    pn_cfg, rep_idx=1, treat_idx=pos_i + 1,
                    env_idx=env_idx + 1 if location_list else 0
                ))
            df_loc['小区号'] = _pn_col
            all_dfs.append(df_loc)
        
        df_design = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]
        
        n_ck = len(df_design[df_design['类型'] == '对照'])
        n_tests_cnt = len(df_design[df_design['类型'] == '测试'])
        loc_info = f" × {len(locs)} 地点" if location_list else ""
        
        st.success(f"✅ 已生成间比法设计：{n_tests_cnt} 测试 + {n_ck} 对照 = {len(df_design)} 个小区{loc_info}")
        
        # 显示设计
        if location_list:
            for loc in locs:
                st.markdown(f"#### 📋 {loc} — 间比法排列")
                df_loc = df_design[df_design['地点'] == loc].drop(columns=['地点'])
                st.dataframe(df_loc, use_container_width=True)
                fig = visualize_interval_design_v3(df_loc, ck_configs)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("#### 📋 间比法排列")
            st.dataframe(df_design, use_container_width=True)
            fig = visualize_interval_design_v3(df_design, ck_configs)
            st.plotly_chart(fig, use_container_width=True)
        
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载间比法设计方案 (CSV)", csv, "间比法设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def generate_interval_design_v3(tests, ck_configs, seed=42):
    """
    生成间比法设计 - 支持起始位置和品种名称
    
    参数:
        tests: 测试处理列表
        ck_configs: 对照配置列表，如 [('品种名', 起始位置, 间隔), ...]
        seed: 随机种子
    
    排列规律：
        - 每个对照从各自的起始位置开始，按间隔循环出现
        - 处理填入非对照位置
    """
    np.random.seed(seed)
    shuffled_tests = list(np.random.permutation(tests))
    
    n_tests = len(shuffled_tests)
    
    # 估算总长度
    est_ck_count = sum((n_tests + start) // intv + 1 for _, start, intv in ck_configs)
    total_len = n_tests + est_ck_count + 10
    
    # 用NumPy数组标记对照位置（存储品种名）
    ck_array = np.zeros(total_len + 1, dtype='U50')  # 空字符串表示非对照
    ck_types = np.zeros(total_len + 1, dtype='U50')  # 存储对照类型标识
    
    for idx, (name, start, intv) in enumerate(ck_configs):
        ck_type = f"CK{idx+1}"  # 用于可视化的类型标识
        for pos in range(start, total_len + 1, intv):
            if pos <= total_len:
                ck_array[pos] = name  # 品种名
                ck_types[pos] = ck_type  # 类型标识
    
    # 构建结果列表
    results = []
    test_idx = 0
    
    for plot_num in range(1, total_len + 1):
        if ck_array[plot_num]:  # 对照位置
            results.append({
                '位置': plot_num,
                '处理': ck_array[plot_num],
                '类型': '对照',
                '对照类别': ck_types[plot_num]
            })
        elif test_idx < n_tests:  # 测试处理
            results.append({
                '位置': plot_num,
                '处理': shuffled_tests[test_idx],
                '类型': '测试',
                '对照类别': None
            })
            test_idx += 1
        else:
            break  # 达到测试数即可结束
    
    # 确保首尾都是CK1对照
    ck1_name = ck_configs[0][0] if ck_configs else 'CK1'
    ck1_type = 'CK1'

    # 确保开头是CK1
    if not results or results[0]['处理'] != ck1_name:
        results.insert(0, {
            '位置': 0,
            '处理': ck1_name,
            '类型': '对照',
            '对照类别': ck1_type
        })
    # 如果开头是其他CK，替换为CK1
    elif results[0]['处理'] != ck1_name or results[0]['对照类别'] != 'CK1':
        results[0]['处理'] = ck1_name
        results[0]['对照类别'] = ck1_type

    # 确保末尾是CK1（不重复添加）
    if results[-1]['处理'] != ck1_name:
        results.append({
            '位置': results[-1]['位置'] + 1,
            '处理': ck1_name,
            '类型': '对照',
            '对照类别': ck1_type
        })
    # 如果末尾是其他CK，替换为CK1
    elif results[-1]['对照类别'] != 'CK1':
        results[-1]['处理'] = ck1_name
        results[-1]['对照类别'] = ck1_type
    
    # 重新编排连续的位置号
    for i, item in enumerate(results):
        item['位置'] = i + 1
    
    # 构建DataFrame
    df = pd.DataFrame(results)
    df.insert(0, '小区号', range(1, len(df) + 1))
    df.insert(1, '区段', 1)
    
    return df


def visualize_interval_design_v3(df, ck_configs):
    """可视化间比法设计 - 按对照类型着色"""
    fig = go.Figure()
    
    # 对照颜色映射
    ck_colors = {
        'CK1': '#e74c3c', 
        'CK2': '#f39c12', 
        'CK3': '#9b59b6', 
        'CK4': '#1abc9c', 
        'CK5': '#34495e'
    }
    test_color = '#3498db'
    
    # 绘制测试处理
    test_data = df[df['类型'] == '测试']
    if len(test_data) > 0:
        fig.add_trace(go.Scatter(
            x=test_data['位置'], y=[1]*len(test_data),
            mode='markers',
            marker=dict(size=15, color=test_color, symbol='circle'),
            name=f'测试 ({len(test_data)}个)',
            text=test_data['处理'], hoverinfo='text'
        ))
    
    # 按对照类型绘制
    for idx, (ck_name, start, intv) in enumerate(ck_configs):
        ck_type = f"CK{idx+1}"
        ck_data = df[df['对照类别'] == ck_type]
        if len(ck_data) > 0:
            fig.add_trace(go.Scatter(
                x=ck_data['位置'], y=[1]*len(ck_data),
                mode='markers',
                marker=dict(size=22, color=ck_colors.get(ck_type, '#808080'), symbol='square'),
                name=f'{ck_name} (起{intv})',
                text=[f"{ck_name}<br>位置:{pos}" for pos in ck_data['位置']], 
                hoverinfo='text'
            ))
    
    # 图例显示对照设置信息
    interval_info = ' | '.join([f"{name}:起{start}间{intv}" for name, start, intv in ck_configs])
    
    fig.update_layout(
        title=f"间比法排列 ({interval_info})",
        xaxis=dict(title='小区位置', tickmode='linear', dtick=5),
        yaxis=dict(title='', showticklabels=False, range=[0.5, 1.5]),
        height=280,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    
    return fig




# ========== 对比法设计 ==========

def contrast_design():
    """对比法设计 - 处理与相邻对照比较"""
    st.markdown("### ⚖️ 对比法设计")
    
    st.info("""
    **对比法**是简单的品种比较设计：
    - 每个处理两侧各有一个对照（CK1）
    - 理论对照 = (左CK1 + 右CK1) / 2
    - 相对产量 = (处理产量 / 理论对照) × 100%
    - 精度高，但对照占地面积大（50%）
    
    **排列格式**：CK — 处理 — CK — 处理 — CK ...
    """)
    
    # 多点设置
    with st.expander("🌍 多点试验设置（可选）", expanded=False):
        locations_input = st.text_area(
            "试验地点列表（每行一个，留空则为单点试验）",
            value="",
            height=80,
            key="contrast_locations",
            placeholder="北京\n天津\n石家庄"
        )
        location_list = [l.strip() for l in locations_input.split('\n') if l.strip()]
        all_same_order = st.checkbox("所有地点排列顺序一致", value=False, key="contrast_same_order")
    
    col1, col2 = st.columns(2)
    with col1:
        treatments = create_text_input_with_file_import(
            "测试处理（每行一个）", 
            "品种A\n品种B\n品种C\n品种D\n品种E\n品种F", 
            height=150,
            key="contrast_treatments"
        )
        treatment_list = [t.strip() for t in treatments.split('\n') if t.strip()]
    
    with col2:
        use_random_seed = st.checkbox("使用随机种子", value=True)
        if not use_random_seed:
            seed = st.number_input("固定随机种子", min_value=1, max_value=9999, value=42)
    
    pn_cfg = plot_number_settings(has_environment=len(location_list) > 0, key_prefix="contrast")
    
    if st.button("生成对比法设计方案"):
        if use_random_seed:
            seed = int(pd.Timestamp.now().timestamp()) % 10000
        
        # 单点 or 多点
        locs = location_list if location_list else [""]
        base_seed = seed
        all_dfs = []
        
        for env_idx, loc in enumerate(locs):
            loc_seed = base_seed if (all_same_order or not location_list) else (base_seed + env_idx * 31)
            df_loc = generate_contrast_design(treatment_list, loc_seed)
            if location_list:
                df_loc.insert(0, '地点', loc)
            # 重新计算小区号
            _pn_col = []
            for pos_i, _ in enumerate(df_loc.iterrows()):
                _pn_col.append(calculate_plot_number(
                    pn_cfg, rep_idx=1, treat_idx=pos_i + 1,
                    env_idx=env_idx + 1 if location_list else 0
                ))
            df_loc['小区号'] = _pn_col
            all_dfs.append(df_loc)
        
        df_design = pd.concat(all_dfs, ignore_index=True) if len(all_dfs) > 1 else all_dfs[0]
        
        loc_info = f" × {len(locs)} 地点" if location_list else ""
        st.success(f"✅ 已生成对比法设计：{len(treatment_list)} 处理{loc_info}，共 {len(df_design)} 个小区")
        
        # 显示设计
        if location_list:
            for loc in locs:
                st.markdown(f"#### 📋 {loc} — 对比法排列")
                df_loc = df_design[df_design['地点'] == loc].drop(columns=['地点'])
                st.dataframe(df_loc, use_container_width=True)
                fig = visualize_contrast_design(df_loc, treatment_list)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("#### 📋 对比法排列")
            st.dataframe(df_design, use_container_width=True)
            fig = visualize_contrast_design(df_design, treatment_list)
            st.plotly_chart(fig, use_container_width=True)
        
        csv = df_design.to_csv(index=False).encode('utf-8-sig')
        if can_download():
            st.download_button("📥 下载对比法设计方案 (CSV)", csv, "对比法设计方案.csv", "text/csv")
        else:
            st.warning("分析次数已用完，充值后可下载结果。请前往侧边栏充值中心。")



def generate_contrast_design(treatments, seed):
    """生成对比法设计
    
    排列格式：CK — 处理 — CK — 处理 — ... — 处理 — CK
    末尾补一个CK，但如果最后一个处理后面已经有CK则不重复。
    """
    plots = []
    np.random.shuffle(treatments)
    
    for i, treat in enumerate(treatments):
        plots.append({'位置': len(plots)+1, '处理': 'CK', '类型': '对照', '配对处理': treat, '小区号': len(plots)+1})
        plots.append({'位置': len(plots)+1, '处理': treat, '类型': '测试', '配对处理': 'CK', '小区号': len(plots)+1})
    
    # 确保末尾是CK（当前末尾是处理，需要补一个CK）
    if plots and plots[-1]['类型'] != '对照':
        plots.append({'位置': len(plots)+1, '处理': 'CK', '类型': '对照', '配对处理': None, '小区号': len(plots)+1})
    
    # 重新编号位置和小区号
    for i, p in enumerate(plots):
        p['位置'] = i + 1
        p['小区号'] = i + 1
    
    return pd.DataFrame(plots)


def visualize_contrast_design(df, treatments):
    """可视化对比法设计"""
    fig = go.Figure()
    colors = {'对照': '#e74c3c', '测试': '#3498db'}
    
    for _, row in df.iterrows():
        fig.add_trace(go.Scatter(
            x=[row['位置']], y=[1],
            mode='markers+text',
            marker=dict(size=50, color=colors.get(row['类型'], '#808080'),
                       symbol='square' if row['类型'] == '对照' else 'circle'),
            text=row['处理'], textposition='middle center', showlegend=False
        ))
    
    fig.update_layout(title="对比法排列", xaxis=dict(title='位置'), yaxis=dict(visible=False), height=200)
    return fig


if __name__ == "__main__":
    import os
    render_experimental_design()
