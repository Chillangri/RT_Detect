import argparse
import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import logging
from datetime import datetime

try:
    import openpyxl
    from openpyxl.styles import Font
except ImportError:
    Font = None

from data_loader import DataLoader
from algorithm import RTAlgorithm

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Real-time Outlier Detection Pipeline (Interactive)")
    parser.add_argument("--t", type=float, default=0.5, help="데이터 수집 주기 (초)")
    parser.add_argument("--n", type=int, default=4, help="한 번에 처리할 표본 수")
    return parser.parse_args()


def interactive_setup(n_samples: int):
    """사용자로부터 분석 설정을 대화형으로 입력받습니다."""
    source_dir = './source'
    files = sorted(glob.glob(os.path.join(source_dir, '*.*')))
    valid_files = [f for f in files if f.endswith(('.csv', '.xlsx', '.xls'))]

    if not valid_files:
        logger.error(f"{source_dir} 폴더에 처리할 파일이 없습니다.")
        return None, None, None, 0, 300, 'FFT', 0.15

    print("\n[ 분석 대상 파일 선택 ]")
    for idx, f in enumerate(valid_files):
        print(f"  {idx + 1}. {os.path.basename(f)}")

    while True:
        try:
            file_idx = int(input(f"파일 번호를 선택하세요 (1~{len(valid_files)}): ")) - 1
            if 0 <= file_idx < len(valid_files):
                selected_file = valid_files[file_idx]
                break
            else:
                print("잘못된 번호입니다. 다시 입력하세요.")
        except ValueError:
            print("숫자를 입력하세요.")

    try:
        if selected_file.endswith('.csv'):
            temp_df = pd.read_csv(selected_file, nrows=0)
        else:
            temp_df = pd.read_excel(selected_file, nrows=0)
        columns = temp_df.columns.tolist()
    except Exception as e:
        logger.error(f"파일 헤더를 읽는 중 오류가 발생했습니다: {e}")
        return None, None, None, 0, 300, 'FFT', 0.15

    print("\n[ 칼럼 목록 ]")
    for idx, col in enumerate(columns):
        print(f"  {idx + 1}. {col}")

    group_cols = []
    while True:
        g_input = input("\nGrouping 기준이 되는 칼럼 번호를 선택하세요 (복수일 경우 쉼표로 구분, 없으면 0 입력): ")
        try:
            g_indices = [int(x.strip()) - 1 for x in g_input.split(',')]
            if len(g_indices) == 1 and g_indices[0] == -1:
                break
            valid = all(0 <= i < len(columns) for i in g_indices)
            if valid and len(g_indices) > 0:
                group_cols = [columns[i] for i in g_indices]
                break
            else:
                print("유효한 번호를 쉼표로 구분하여 입력하거나 0을 입력하세요.")
        except ValueError:
            print("숫자 형식으로 입력하세요.")

    target_cols = []
    while True:
        t_input = input("\n분석 대상이 되는 데이터 칼럼 번호를 선택하세요 (복수일 경우 쉼표로 구분): ")
        try:
            t_indices = [int(x.strip()) - 1 for x in t_input.split(',')]
            valid = all(0 <= i < len(columns) for i in t_indices)
            if valid and len(t_indices) > 0:
                target_cols = [columns[i] for i in t_indices]
                break
            else:
                print("유효한 번호를 쉼표로 구분하여 입력하세요.")
        except ValueError:
            print("숫자 형식으로 입력하세요.")

    alpha = 0.15
    while True:
        a_input = input("\nEWMA 평균/분산 업데이트에 사용할 alpha 값을 입력하세요 (기본 0.15): ")
        if not a_input.strip():
            break
        try:
            alpha = float(a_input.strip())
            if 0 < alpha <= 1:
                break
            else:
                print("0보다 크고 1 이하의 숫자를 입력하세요.")
        except ValueError:
            print("숫자 형식으로 입력하세요.")

    if n_samples == 1:
        min_ignore = 10
        ignore_init = 10
        prompt_msg = f"\n각 그룹별 초기 무시할 데이터 개수를 입력하세요 (최소 {min_ignore}, 기본 {ignore_init}): "
    else:
        min_ignore = 2
        ignore_init = 2
        prompt_msg = f"\n각 그룹별 초기 무시할 부분군(Chunk) 수를 입력하세요 (최소 {min_ignore}, 기본 {ignore_init}): "

    while True:
        i_input = input(prompt_msg)
        if not i_input.strip():
            break
        try:
            val = int(i_input.strip())
            if val >= min_ignore:
                ignore_init = val
                break
            else:
                print(f"{min_ignore} 이상의 숫자를 입력하세요.")
        except ValueError:
            print("숫자 형식으로 입력하세요.")

    display_limit = 300
    while True:
        d_input = input("\n한 화면에 표시할 최대 점(부분군 평균) 개수를 입력하세요 (기본 300): ")
        if not d_input.strip():
            break
        try:
            display_limit = int(d_input.strip())
            if display_limit > 0:
                break
            else:
                print("1 이상의 숫자를 입력하세요.")
        except ValueError:
            print("숫자 형식으로 입력하세요.")

    basis_map = {'1': 'Raw', '2': 'FFT', '3': 'Kalman'}
    basis = 'FFT'
    while True:
        b_input = input("\n이상치 판정 기준을 선택하세요 (1: Raw, 2: FFT, 3: Kalman) [기본 2]: ")
        if not b_input.strip():
            break
        if b_input.strip() in basis_map:
            basis = basis_map[b_input.strip()]
            break
        print("1, 2, 3 중 하나를 입력하세요.")

    baseline_size = 30
    while True:
        bs_input = input(f"\n기저선(Baseline) 산정에 필요한 데이터 숫자를 입력하세요 (기본 {baseline_size}): ")
        if not bs_input.strip():
            break
        try:
            val = int(bs_input.strip())
            if val > 1:
                baseline_size = val
                break
            else:
                print("2 이상의 숫자를 입력하세요.")
        except ValueError:
            print("숫자 형식으로 입력하세요.")

    return selected_file, group_cols, target_cols, ignore_init, display_limit, basis, alpha, baseline_size


def create_group_plot(target_cols: list, group_val_str: str, basis: str, n_samples: int) -> tuple:
    """
    그룹 전용 새 plot 창(figs, lines)을 생성하고 반환합니다.
    평균 관리도와 변동 관리도가 상하 쌍으로 표시되도록 subplots(2, 1)을 생성합니다.

    Returns:
        (figs, lines): 그룹 별 figure 딕셔너리와 plot 데이터 딕셔너리
    """
    figs = {}
    lines = {}
    
    if n_samples == 1:
        disp_title = "Moving Range (MR)"
        mean_title_suffix = "(Individual X)"
    elif 2 <= n_samples <= 5:
        disp_title = "Range (R)"
        mean_title_suffix = "(X-bar)"
    else:
        disp_title = "Standard Deviation (s)"
        mean_title_suffix = "(X-bar)"

    for col in target_cols:
        fig, (ax_mean, ax_disp) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        title_mean = f'Target: {col} {mean_title_suffix}'
        title_disp = f'Target: {col} {disp_title} Chart'
        if group_val_str:
            title_mean += f' | Group: {group_val_str}'

        fig.canvas.manager.set_window_title(f'Target: {col}')
        ax_mean.set_title(title_mean)
        ax_mean.set_ylabel('Value / Mean')
        ax_mean.grid(True, alpha=0.5)

        ax_disp.set_title(title_disp)
        ax_disp.set_xlabel('Chunk Index')
        ax_disp.set_ylabel('Dispersion')
        ax_disp.grid(True, alpha=0.5)

        # ── 평균 관리도 플롯 라인 정의 ──
        line_baseline, = ax_mean.plot([], [], label='Baseline Mean', color='gray', linestyle='-', linewidth=2.0, zorder=2)
        line_raw, = ax_mean.plot([], [], label='Raw Mean', color='lightgray', alpha=0.8, marker='o', markersize=3, linewidth=1.5, zorder=2)
        line_fft, = ax_mean.plot([], [], label='FFT Mean', color='orange', alpha=0.85, marker='s', markersize=3, linewidth=1.2, linestyle='--', zorder=3)
        line_kalman, = ax_mean.plot([], [], label='Kalman Mean', color='dodgerblue', alpha=0.85, marker='^', markersize=3, linewidth=1.2, linestyle='-.', zorder=4)
        line_ucl, = ax_mean.plot([], [], label=f'UCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        line_lcl, = ax_mean.plot([], [], label=f'LCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        line_ucl_welford, = ax_mean.plot([], [], label='UCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)
        line_lcl_welford, = ax_mean.plot([], [], label='LCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)
        scatter_outlier = ax_mean.scatter([], [], color='red', zorder=5, s=50, label=f'Outlier ({basis})')
        ax_mean.legend(loc='upper right', fontsize=7)

        # ── 변동 관리도 플롯 라인 정의 ──
        line_baseline_disp, = ax_disp.plot([], [], label='Baseline Disp', color='gray', linestyle='-', linewidth=2.0, zorder=2)
        line_raw_disp, = ax_disp.plot([], [], label='Raw Disp', color='lightgray', alpha=0.8, marker='o', markersize=3, linewidth=1.5, zorder=2)
        line_fft_disp, = ax_disp.plot([], [], label='FFT Disp', color='orange', alpha=0.85, marker='s', markersize=3, linewidth=1.2, linestyle='--', zorder=3)
        line_kalman_disp, = ax_disp.plot([], [], label='Kalman Disp', color='dodgerblue', alpha=0.85, marker='^', markersize=3, linewidth=1.2, linestyle='-.', zorder=4)
        line_ucl_disp, = ax_disp.plot([], [], label=f'UCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        line_lcl_disp, = ax_disp.plot([], [], label=f'LCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        line_ucl_welford_disp, = ax_disp.plot([], [], label='UCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)
        line_lcl_welford_disp, = ax_disp.plot([], [], label='LCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)
        scatter_outlier_disp = ax_disp.scatter([], [], color='red', zorder=5, s=50, label=f'Outlier ({basis})')
        ax_disp.legend(loc='upper right', fontsize=7)

        figs[col] = fig
        lines[col] = {
            'ax_mean': ax_mean,
            'ax_disp': ax_disp,
            'baseline': line_baseline,
            'raw': line_raw,
            'fft': line_fft,
            'kalman': line_kalman,
            'ucl': line_ucl,
            'lcl': line_lcl,
            'ucl_welford': line_ucl_welford,
            'lcl_welford': line_lcl_welford,
            'outlier': scatter_outlier,
            
            'baseline_disp': line_baseline_disp,
            'raw_disp': line_raw_disp,
            'fft_disp': line_fft_disp,
            'kalman_disp': line_kalman_disp,
            'ucl_disp': line_ucl_disp,
            'lcl_disp': line_lcl_disp,
            'ucl_welford_disp': line_ucl_welford_disp,
            'lcl_welford_disp': line_lcl_welford_disp,
            'outlier_disp': scatter_outlier_disp,

            'vlines_mean_shift': None,
            'shift_texts_mean': [],
            'vlines_var_spike': None,
            'shift_texts_disp': [],

            'x_data': [],
            'baseline_y': [],
            'raw_y': [],
            'fft_y': [],
            'kalman_y': [],
            'ucl_y': [],
            'lcl_y': [],
            'ucl_welford_y': [],
            'lcl_welford_y': [],
            'outlier_x': [],
            'outlier_y': [],
            'mean_shift_x': [],

            'baseline_disp_y': [],
            'raw_disp_y': [],
            'fft_disp_y': [],
            'kalman_disp_y': [],
            'ucl_disp_y': [],
            'lcl_disp_y': [],
            'ucl_welford_disp_y': [],
            'lcl_welford_disp_y': [],
            'outlier_disp_x': [],
            'outlier_disp_y': [],
            'var_spike_x': [],
        }
        fig.tight_layout()
        fig.show()

    return figs, lines


def update_plot(lines: dict, figs: dict, target_cols: list, display_limit: int):
    """
    현재 활성화된 그룹의 plot을 갱신합니다.
    display_limit 이상이면 좌측 스크롤(슬라이딩 윈도우)이 적용됩니다.
    """
    for col in target_cols:
        if col not in lines:
            continue
        ld = lines[col]

        x_all = ld['x_data']
        x_slice = x_all[-display_limit:]
        if not x_slice:
            continue

        min_x = x_slice[0]

        # ── 평균 차트 라인 업데이트 ──
        ld['baseline'].set_data(x_slice, ld['baseline_y'][-display_limit:])
        ld['raw'].set_data(x_slice, ld['raw_y'][-display_limit:])
        ld['fft'].set_data(x_slice, ld['fft_y'][-display_limit:])
        ld['kalman'].set_data(x_slice, ld['kalman_y'][-display_limit:])
        ld['ucl'].set_data(x_slice, ld['ucl_y'][-display_limit:])
        ld['lcl'].set_data(x_slice, ld['lcl_y'][-display_limit:])
        ld['ucl_welford'].set_data(x_slice, ld['ucl_welford_y'][-display_limit:])
        ld['lcl_welford'].set_data(x_slice, ld['lcl_welford_y'][-display_limit:])

        # Outlier: display_limit 범위 내의 포인트만 표시
        if ld['outlier_x']:
            out_pairs = [(ox, oy) for ox, oy in zip(ld['outlier_x'], ld['outlier_y']) if ox >= min_x]
            if out_pairs:
                ld['outlier'].set_offsets(out_pairs)
            else:
                ld['outlier'].set_offsets(np.empty((0, 2)))
        else:
            ld['outlier'].set_offsets(np.empty((0, 2)))

        ax_mean = ld['ax_mean']
        ax_mean.relim()
        ax_mean.autoscale_view()

        # Mean Shift 수직선 및 텍스트 표시
        if ld['vlines_mean_shift'] is not None:
            ld['vlines_mean_shift'].remove()
            ld['vlines_mean_shift'] = None
        for txt in ld['shift_texts_mean']:
            txt.remove()
        ld['shift_texts_mean'].clear()
        
        valid_ms_x = [x for x in ld['mean_shift_x'] if x >= min_x]
        if valid_ms_x:
            ymin, ymax = ax_mean.get_ylim()
            ld['vlines_mean_shift'] = ax_mean.vlines(valid_ms_x, ymin, ymax, color='red', alpha=0.5, linestyle='-', zorder=1)
            for x in valid_ms_x:
                txt = ax_mean.text(x, ymax, str(x), color='red', rotation=90, va='top', ha='right', fontsize=8)
                ld['shift_texts_mean'].append(txt)

        # ── 변동 차트 라인 업데이트 ──
        ld['baseline_disp'].set_data(x_slice, ld['baseline_disp_y'][-display_limit:])
        ld['raw_disp'].set_data(x_slice, ld['raw_disp_y'][-display_limit:])
        ld['fft_disp'].set_data(x_slice, ld['fft_disp_y'][-display_limit:])
        ld['kalman_disp'].set_data(x_slice, ld['kalman_disp_y'][-display_limit:])
        ld['ucl_disp'].set_data(x_slice, ld['ucl_disp_y'][-display_limit:])
        ld['lcl_disp'].set_data(x_slice, ld['lcl_disp_y'][-display_limit:])
        ld['ucl_welford_disp'].set_data(x_slice, ld['ucl_welford_disp_y'][-display_limit:])
        ld['lcl_welford_disp'].set_data(x_slice, ld['lcl_welford_disp_y'][-display_limit:])

        if ld['outlier_disp_x']:
            out_disp_pairs = [(ox, oy) for ox, oy in zip(ld['outlier_disp_x'], ld['outlier_disp_y']) if ox >= min_x]
            if out_disp_pairs:
                ld['outlier_disp'].set_offsets(out_disp_pairs)
            else:
                ld['outlier_disp'].set_offsets(np.empty((0, 2)))
        else:
            ld['outlier_disp'].set_offsets(np.empty((0, 2)))

        ax_disp = ld['ax_disp']
        ax_disp.relim()
        ax_disp.autoscale_view()

        # Variance Spike 수직선 및 텍스트 표시
        if ld['vlines_var_spike'] is not None:
            ld['vlines_var_spike'].remove()
            ld['vlines_var_spike'] = None
        for txt in ld['shift_texts_disp']:
            txt.remove()
        ld['shift_texts_disp'].clear()
        
        valid_vs_x = [x for x in ld['var_spike_x'] if x >= min_x]
        if valid_vs_x:
            ymin, ymax = ax_disp.get_ylim()
            ld['vlines_var_spike'] = ax_disp.vlines(valid_vs_x, ymin, ymax, color='blue', alpha=0.5, linestyle='-', zorder=1)
            for x in valid_vs_x:
                txt = ax_disp.text(x, ymax, str(x), color='blue', rotation=90, va='top', ha='right', fontsize=8)
                ld['shift_texts_disp'].append(txt)

        figs[col].canvas.draw()
        figs[col].canvas.flush_events()


def plot_and_save_pdf(pdf_obj, data_subset: pd.DataFrame, col_name: str, grp_name: str, basis: str, n_samples: int):
    """단일 칼럼 + 단일 그룹의 결과를 평균 및 변동 2단 구성으로 PDF 페이지 하나에 저장합니다."""
    fig_pdf, (ax_mean, ax_disp) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    if n_samples == 1:
        disp_title = "Moving Range (MR)"
        mean_title_suffix = "(Individual X)"
    elif 2 <= n_samples <= 5:
        disp_title = "Range (R)"
        mean_title_suffix = "(X-bar)"
    else:
        disp_title = "Standard Deviation (s)"
        mean_title_suffix = "(X-bar)"

    # ── 1. 상단: 평균 관리도 시각화 ──
    if 'Baseline_Mean' in data_subset.columns:
        ax_mean.plot(data_subset['chunk_idx'], data_subset['Baseline_Mean'], label='Baseline Mean', color='gray', linewidth=2.0, zorder=1)
    ax_mean.plot(data_subset['chunk_idx'], data_subset['raw'], label='Raw Mean', color='lightgray', alpha=0.8, marker='o', markersize=3, linewidth=1.5, zorder=2)
    ax_mean.plot(data_subset['chunk_idx'], data_subset['fft'], label='FFT Mean', color='orange', alpha=0.85, marker='s', markersize=3, linewidth=1.2, linestyle='--', zorder=3)
    ax_mean.plot(data_subset['chunk_idx'], data_subset['kalman'], label='Kalman Mean', color='dodgerblue', alpha=0.85, marker='^', markersize=3, linewidth=1.2, linestyle='-.', zorder=4)

    valid_idx = data_subset['ucl'].notnull() & data_subset['lcl'].notnull()
    if valid_idx.any():
        sub_valid = data_subset[valid_idx]
        ax_mean.plot(sub_valid['chunk_idx'], sub_valid['ucl'], label=f'UCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        ax_mean.plot(sub_valid['chunk_idx'], sub_valid['lcl'], label=f'LCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        ax_mean.fill_between(sub_valid['chunk_idx'],
                            sub_valid['lcl'].astype(float),
                            sub_valid['ucl'].astype(float),
                            color='red', alpha=0.08)

    valid_welford_idx = data_subset['ucl_welford'].notnull() & data_subset['lcl_welford'].notnull()
    if valid_welford_idx.any():
        sub_valid_welford = data_subset[valid_welford_idx]
        ax_mean.plot(sub_valid_welford['chunk_idx'], sub_valid_welford['ucl_welford'], label='UCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)
        ax_mean.plot(sub_valid_welford['chunk_idx'], sub_valid_welford['lcl_welford'], label='LCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)

    outlier_pts = data_subset[data_subset['is_outlier'] == True]
    if not outlier_pts.empty:
        ax_mean.scatter(outlier_pts['chunk_idx'], outlier_pts['basis_val'],
                       color='red', s=60, label=f'Outlier ({basis})', zorder=5)

    if 'Mean_Shift' in data_subset.columns:
        ms_pts = data_subset[data_subset['Mean_Shift'] == True]
        if not ms_pts.empty:
            ymin, ymax = ax_mean.get_ylim()
            ax_mean.vlines(ms_pts['chunk_idx'], ymin, ymax, color='red', alpha=0.5, linestyle='-', zorder=1)
            for x in ms_pts['chunk_idx']:
                ax_mean.text(x, ymax, str(int(x)), color='red', rotation=90, va='top', ha='right', fontsize=8)

    title_mean = f'Target: {col_name} {mean_title_suffix}'
    if grp_name:
        title_mean += f' | Group: {grp_name}'
    ax_mean.set_title(title_mean, fontsize=12)
    ax_mean.set_ylabel('Mean Value')
    ax_mean.legend(fontsize=8, loc='upper right')
    ax_mean.grid(True, alpha=0.4)

    # ── 2. 하단: 변동 관리도 시각화 ──
    if 'Baseline_Disp' in data_subset.columns:
        ax_disp.plot(data_subset['chunk_idx'], data_subset['Baseline_Disp'], label='Baseline Disp', color='gray', linewidth=2.0, zorder=1)
    ax_disp.plot(data_subset['chunk_idx'], data_subset['raw_disp'], label='Raw Disp', color='lightgray', alpha=0.8, marker='o', markersize=3, linewidth=1.5, zorder=2)
    ax_disp.plot(data_subset['chunk_idx'], data_subset['fft_disp'], label='FFT Disp', color='orange', alpha=0.85, marker='s', markersize=3, linewidth=1.2, linestyle='--', zorder=3)
    ax_disp.plot(data_subset['chunk_idx'], data_subset['kalman_disp'], label='Kalman Disp', color='dodgerblue', alpha=0.85, marker='^', markersize=3, linewidth=1.2, linestyle='-.', zorder=4)

    valid_disp_idx = data_subset['ucl_disp'].notnull() & data_subset['lcl_disp'].notnull()
    if valid_disp_idx.any():
        sub_valid_disp = data_subset[valid_disp_idx]
        ax_disp.plot(sub_valid_disp['chunk_idx'], sub_valid_disp['ucl_disp'], label=f'UCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        ax_disp.plot(sub_valid_disp['chunk_idx'], sub_valid_disp['lcl_disp'], label=f'LCL ({basis})', color='red', linestyle='--', linewidth=1.2)
        ax_disp.fill_between(sub_valid_disp['chunk_idx'],
                            sub_valid_disp['lcl_disp'].astype(float),
                            sub_valid_disp['ucl_disp'].astype(float),
                            color='red', alpha=0.08)

    valid_welford_disp_idx = data_subset['ucl_welford_disp'].notnull() & data_subset['lcl_welford_disp'].notnull()
    if valid_welford_disp_idx.any():
        sub_valid_welford_disp = data_subset[valid_welford_disp_idx]
        ax_disp.plot(sub_valid_welford_disp['chunk_idx'], sub_valid_welford_disp['ucl_welford_disp'], label='UCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)
        ax_disp.plot(sub_valid_welford_disp['chunk_idx'], sub_valid_welford_disp['lcl_welford_disp'], label='LCL (Welford)', color='lightgray', linestyle='--', linewidth=1.5, alpha=0.8, zorder=2)

    outlier_disp_pts = data_subset[data_subset['is_outlier_disp'] == True]
    if not outlier_disp_pts.empty:
        ax_disp.scatter(outlier_disp_pts['chunk_idx'], outlier_disp_pts['basis_disp_val'],
                       color='red', s=60, label=f'Outlier ({basis})', zorder=5)

    if 'Variance_Spike' in data_subset.columns:
        vs_pts = data_subset[data_subset['Variance_Spike'] == True]
        if not vs_pts.empty:
            ymin, ymax = ax_disp.get_ylim()
            ax_disp.vlines(vs_pts['chunk_idx'], ymin, ymax, color='blue', alpha=0.5, linestyle='-', zorder=1)
            for x in vs_pts['chunk_idx']:
                ax_disp.text(x, ymax, str(int(x)), color='blue', rotation=90, va='top', ha='right', fontsize=8)

    ax_disp.set_title(f'Target: {col_name} {disp_title} Chart', fontsize=12)
    ax_disp.set_xlabel('Chunk Index')
    ax_disp.set_ylabel('Dispersion')
    ax_disp.legend(fontsize=8, loc='upper right')
    ax_disp.grid(True, alpha=0.4)

    fig_pdf.tight_layout()
    pdf_obj.savefig(fig_pdf)
    plt.close(fig_pdf)


def save_excel(excel_results: dict, target_cols: list, n_samples: int, basis: str,
               output_dir: str, timestamp: str, base_filename: str):
    """
    분석 칼럼별로 엑셀 파일을 저장합니다.
    평균 및 변동 수치와 종합 판정이 적용된 굵은 글씨 포맷팅을 지원합니다.
    """
    if not excel_results:
        return

    for col in target_cols:
        rows = excel_results.get(col, [])
        if not rows:
            logger.warning(f"칼럼 [{col}] 에 저장할 데이터가 없습니다.")
            continue

        df_excel = pd.DataFrame(rows)
        safe_col = str(col).replace('/', '_').replace('\\', '_').replace(' ', '_')

        if len(target_cols) > 1:
            excel_filename = f"{timestamp}_{base_filename}_{safe_col}.xlsx"
        else:
            excel_filename = f"{timestamp}_{base_filename}.xlsx"

        excel_path = os.path.join(output_dir, excel_filename)

        try:
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df_excel.to_excel(writer, sheet_name='Results', index=False)
                worksheet = writer.sheets['Results']

                if Font:
                    bold_font = Font(bold=True)
                    red_font = Font(color="FF0000", bold=True)
                    blue_font = Font(color="0000FF", bold=True)
                    purple_font = Font(color="800080", bold=True)
                    
                    # 칼럼명 볼드체 처리
                    for col_idx_excel, col_name in enumerate(df_excel.columns, 1):
                        is_bold = (
                            (basis == 'Raw' and col_name in ('Raw_평균', 'Raw_변동', 'Outlier_Raw_평균', 'Outlier_Raw_변동', '종합_Outlier_Raw')) or
                            (basis == 'FFT' and col_name in ('FFT_평균', 'FFT_변동', 'Outlier_FFT_평균', 'Outlier_FFT_변동', '종합_Outlier_FFT')) or
                            (basis == 'Kalman' and col_name in ('Kalman_평균', 'Kalman_변동', 'Outlier_Kalman_평균', 'Outlier_Kalman_변동', '종합_Outlier_Kalman')) or
                            col_name in ('상한_평균(선택기준)', '하한_평균(선택기준)', '상한_변동(선택기준)', '하한_변동(선택기준)')
                        )
                        if is_bold:
                            for row_idx in range(2, len(df_excel) + 2):
                                worksheet.cell(row=row_idx, column=col_idx_excel).font = bold_font

                    # Mean Shift 및 Variance Spike에 따른 행 색상 지정
                    ms_col = 'Mean_Shift'
                    vs_col = 'Variance_Spike'
                    if ms_col in df_excel.columns and vs_col in df_excel.columns:
                        for row_idx, row_series in df_excel.iterrows():
                            is_ms = row_series[ms_col]
                            is_vs = row_series[vs_col]
                            
                            target_font = None
                            if is_ms and is_vs:
                                target_font = purple_font
                            elif is_ms:
                                target_font = red_font
                            elif is_vs:
                                target_font = blue_font
                                
                            if target_font:
                                for col_idx in range(1, len(df_excel.columns) + 1):
                                    worksheet.cell(row=row_idx + 2, column=col_idx).font = target_font

            logger.info(f"엑셀 저장 완료: {excel_path}")
        except Exception as e:
            logger.error(f"엑셀 저장 실패 ({excel_path}): {e}")


def main():
    args = parse_args()

    setup_result = interactive_setup(args.n)
    if setup_result[0] is None:
        return
    selected_file, group_cols, target_cols, ignore_init, display_limit, basis, alpha, baseline_size = setup_result

    logger.info(
        f"파이프라인 시작 (t={args.t}s, n={args.n}, ignore_init={ignore_init}, "
        f"display_limit={display_limit}, basis={basis}, alpha={alpha}, baseline_size={baseline_size})"
    )
    logger.info(f"파일: {selected_file}, 그룹: {group_cols}, 타겟: {target_cols}")

    loader = DataLoader(
        file_path=selected_file,
        n_samples=args.n,
        group_cols=group_cols,
        target_cols=target_cols
    )
    algo = RTAlgorithm(n_subgroup=args.n, alpha=alpha, baseline_size=baseline_size, selected_basis=basis)

    # 결과 누적 저장소
    all_results = []  # PDF 생성용
    excel_results = {col: [] for col in target_cols}  # 엑셀 저장용

    last_group_val = None
    group_chunk_count = 0  # 현재 그룹 내 처리된 chunk 수
    chunk_seq = 0  # 전체 청크 순번 (x축 표시용)

    plt.ion()

    # 현재 활성화된 그룹의 plot 상태 (그룹 변경 시 교체)
    current_figs = {}
    current_lines = {}

    if not group_cols:
        current_figs, current_lines = create_group_plot(target_cols, None, basis, args.n)

    # ── n=1일 때 개별 측정값의 이전 변동 계산을 위한 변수 ──
    last_vals_mean = {col: {'Raw': None, 'FFT': None, 'Kalman': None} for col in target_cols}

    # ────────────────────────────────────────────────
    # 메인 스트리밍 루프
    # ────────────────────────────────────────────────
    try:
        for _, chunk in loader.stream_data():
            if chunk.empty:
                continue

            # chunk 내에서 그룹 값이 중간에 변경되는 경우를 처리하기 위해 블록 분리
            if group_cols:
                group_vals = chunk[group_cols].apply(tuple, axis=1)
                blocks = (group_vals != group_vals.shift()).cumsum()
                sub_chunks = [
                    (sub, tuple(sub[group_cols].iloc[0]))
                    for _, sub in chunk.groupby(blocks, sort=False)
                ]
            else:
                sub_chunks = [(chunk, None)]

            for sub_chunk, current_group_val in sub_chunks:
                # ── 그룹 변경 감지 ──
                if group_cols:
                    if last_group_val is None:
                        current_figs, current_lines = create_group_plot(target_cols, str(current_group_val), basis, args.n)
                        logger.info(f"첫 그룹 시작: {current_group_val}")
                    elif current_group_val != last_group_val:
                        logger.info(f"그룹 변경 감지 ({last_group_val} → {current_group_val}). 알고리즘 초기화 및 새 창 생성.")
                        algo.reset()
                        group_chunk_count = 0
                        chunk_seq = 0  # 새 그룹이므로 x축 인덱스 리셋
                        current_figs, current_lines = create_group_plot(target_cols, str(current_group_val), basis, args.n)
                        # 그룹 변경 시 이전 값 초기화
                        for col in target_cols:
                            last_vals_mean[col] = {'Raw': None, 'FFT': None, 'Kalman': None}
                    last_group_val = current_group_val

                # ── 타겟 칼럼 추출 ──
                target_data = sub_chunk[target_cols].select_dtypes(include=['number'])
                if target_data.empty:
                    continue

                chunk_len = len(sub_chunk)

                # ── 필터 적용 (개별 데이터 스트림 기준) ──
                fft_chunk, kf_chunk = algo.apply_filters(target_data.values, cutoff_ratio=0.5)

                # ── 부분군 평균 계산 (X-bar) ──
                raw_mean_vals = target_data.mean().values    # shape: (n_target_cols,)
                fft_mean_vals = fft_chunk.mean(axis=0)
                kalman_mean_vals = kf_chunk.mean(axis=0)

                # ── 부분군 변동 계산 (MR / R / s) ──
                raw_disp_vals = []
                fft_disp_vals = []
                kalman_disp_vals = []

                for col_idx, col in enumerate(target_data.columns):
                    r_val = target_data.iloc[:, col_idx].values
                    f_val = fft_chunk[:, col_idx]
                    k_val = kf_chunk[:, col_idx]

                    if args.n == 1:
                        # Raw MR
                        if last_vals_mean[col]['Raw'] is None:
                            r_disp = 0.0
                        else:
                            r_disp = abs(raw_mean_vals[col_idx] - last_vals_mean[col]['Raw'])
                        # FFT MR
                        if last_vals_mean[col]['FFT'] is None:
                            f_disp = 0.0
                        else:
                            f_disp = abs(fft_mean_vals[col_idx] - last_vals_mean[col]['FFT'])
                        # Kalman MR
                        if last_vals_mean[col]['Kalman'] is None:
                            k_disp = 0.0
                        else:
                            k_disp = abs(kalman_mean_vals[col_idx] - last_vals_mean[col]['Kalman'])
                    elif 2 <= args.n <= 5:
                        # R = Max - Min
                        r_disp = r_val.max() - r_val.min()
                        f_disp = f_val.max() - f_val.min()
                        k_disp = k_val.max() - k_val.min()
                    else:
                        # s = std(ddof=1)
                        r_disp = r_val.std(ddof=1) if len(r_val) > 1 else 0.0
                        f_disp = f_val.std(ddof=1) if len(f_val) > 1 else 0.0
                        k_disp = k_val.std(ddof=1) if len(k_val) > 1 else 0.0

                    raw_disp_vals.append(r_disp)
                    fft_disp_vals.append(f_disp)
                    kalman_disp_vals.append(k_disp)

                raw_disp_vals = np.array(raw_disp_vals)
                fft_disp_vals = np.array(fft_disp_vals)
                kalman_disp_vals = np.array(kalman_disp_vals)

                # ── 초기 무시 여부 판단 ──
                ignore_flag = group_chunk_count < ignore_init

                # ── Welford 업데이트 ──
                algo.update_welford(target_data.values)

                # ── 통계 업데이트 ──
                if not ignore_flag:
                    algo.update_stats('Raw', target_data.values, raw_mean_vals)
                    algo.update_stats('FFT', fft_chunk, fft_mean_vals)
                    algo.update_stats('Kalman', kf_chunk, kalman_mean_vals)
                else:
                    algo.add_init_data('Raw', target_data.values)
                    algo.add_init_data('FFT', fft_chunk)
                    algo.add_init_data('Kalman', kf_chunk)
                    
                    # 방금 추가한 데이터가 초기 수집의 마지막이라면 초기 EWMA 세팅 진행
                    if group_chunk_count == ignore_init - 1:
                        algo.finalize_init('Raw')
                        algo.finalize_init('FFT')
                        algo.finalize_init('Kalman')

                # ── 관리 한계 계산 (평균 UCL/LCL 및 변동 UCL/LCL) ──
                ucl_raw, lcl_raw, ucl_raw_disp, lcl_raw_disp = algo.get_limits('Raw', sigma_multiplier=3.0)
                ucl_fft, lcl_fft, ucl_fft_disp, lcl_fft_disp = algo.get_limits('FFT', sigma_multiplier=3.0)
                ucl_kalman, lcl_kalman, ucl_kalman_disp, lcl_kalman_disp = algo.get_limits('Kalman', sigma_multiplier=3.0)
                
                ucl_welford, lcl_welford, ucl_welford_disp, lcl_welford_disp = algo.get_welford_limits(sigma_multiplier=3.0)

                # 초기 무시 구간 동안은 한계선 None 처리
                if ucl_raw is None:
                    ucl_welford = None
                    lcl_welford = None
                    ucl_welford_disp = None
                    lcl_welford_disp = None

                # ── Outlier 계산 ──
                # 평균 차트 이상치
                out_raw = algo.detect_outliers(raw_mean_vals, ucl_raw, lcl_raw)
                out_fft = algo.detect_outliers(fft_mean_vals, ucl_fft, lcl_fft)
                out_kalman = algo.detect_outliers(kalman_mean_vals, ucl_kalman, lcl_kalman)

                # 변동 차트 이상치
                out_raw_disp = algo.detect_outliers(raw_disp_vals, ucl_raw_disp, lcl_raw_disp)
                out_fft_disp = algo.detect_outliers(fft_disp_vals, ucl_fft_disp, lcl_fft_disp)
                out_kalman_disp = algo.detect_outliers(kalman_disp_vals, ucl_kalman_disp, lcl_kalman_disp)

                # 초기 무시 구간은 Outlier를 False로 강제
                if ignore_flag:
                    out_raw = np.zeros(len(out_raw), dtype=bool)
                    out_fft = np.zeros(len(out_fft), dtype=bool)
                    out_kalman = np.zeros(len(out_kalman), dtype=bool)
                    out_raw_disp = np.zeros(len(out_raw_disp), dtype=bool)
                    out_fft_disp = np.zeros(len(out_fft_disp), dtype=bool)
                    out_kalman_disp = np.zeros(len(out_kalman_disp), dtype=bool)

                # ── Baseline 업데이트 및 판별 ──
                basis_mean_vals = raw_mean_vals if basis == 'Raw' else (fft_mean_vals if basis == 'FFT' else kalman_mean_vals)
                basis_disp_vals = raw_disp_vals if basis == 'Raw' else (fft_disp_vals if basis == 'FFT' else kalman_disp_vals)
                basis_outliers = out_raw if basis == 'Raw' else (out_fft if basis == 'FFT' else out_kalman)
                
                algo.update_baseline(basis_mean_vals, basis_disp_vals, basis_outliers)
                b_mean, b_disp = algo.get_baseline_stats()
                
                ewma_basis_mean = algo.ewma_mean[basis] if algo.ewma_mean[basis] is not None else np.zeros(len(target_data.columns))
                
                # 시각적으로 나타나는 큰 피크(Variance Spike)를 즉각 인지하기 위해, 평활화된 EWMA 변동 대신 현재 Chunk의 실제 변동값을 사용합니다.
                current_basis_disp = basis_disp_vals
                
                mean_shift, var_spike, _, _ = algo.detect_shifts(b_mean, b_disp, ewma_basis_mean, current_basis_disp)

                # ── 칼럼별 결과 처리 ──
                for col_idx, col in enumerate(target_data.columns):
                    raw_vals = target_data.iloc[:, col_idx].tolist()

                    # n보다 짧은 마지막 chunk는 None으로 패딩
                    pad = args.n - chunk_len
                    raw_vals_padded = raw_vals + [None] * pad

                    # 선택된 기준에 따른 값 및 관리한계/이상치 선택
                    if basis == 'Raw':
                        basis_mean_val = raw_mean_vals[col_idx]
                        basis_disp_val = raw_disp_vals[col_idx]
                        basis_out = bool(out_raw[col_idx])
                        basis_out_disp = bool(out_raw_disp[col_idx])
                        basis_ucl = ucl_raw[col_idx] if ucl_raw is not None else None
                        basis_lcl = lcl_raw[col_idx] if lcl_raw is not None else None
                        basis_ucl_disp = ucl_raw_disp[col_idx] if ucl_raw_disp is not None else None
                        basis_lcl_disp = lcl_raw_disp[col_idx] if lcl_raw_disp is not None else None
                    elif basis == 'FFT':
                        basis_mean_val = fft_mean_vals[col_idx]
                        basis_disp_val = fft_disp_vals[col_idx]
                        basis_out = bool(out_fft[col_idx])
                        basis_out_disp = bool(out_fft_disp[col_idx])
                        basis_ucl = ucl_fft[col_idx] if ucl_fft is not None else None
                        basis_lcl = lcl_fft[col_idx] if lcl_fft is not None else None
                        basis_ucl_disp = ucl_fft_disp[col_idx] if ucl_fft_disp is not None else None
                        basis_lcl_disp = lcl_fft_disp[col_idx] if lcl_fft_disp is not None else None
                    else:  # Kalman
                        basis_mean_val = kalman_mean_vals[col_idx]
                        basis_disp_val = kalman_disp_vals[col_idx]
                        basis_out = bool(out_kalman[col_idx])
                        basis_out_disp = bool(out_kalman_disp[col_idx])
                        basis_ucl = ucl_kalman[col_idx] if ucl_kalman is not None else None
                        basis_lcl = lcl_kalman[col_idx] if lcl_kalman is not None else None
                        basis_ucl_disp = ucl_kalman_disp[col_idx] if ucl_kalman_disp is not None else None
                        basis_lcl_disp = lcl_kalman_disp[col_idx] if lcl_kalman_disp is not None else None

                    welford_ucl_val = ucl_welford[col_idx] if ucl_welford is not None else None
                    welford_lcl_val = lcl_welford[col_idx] if lcl_welford is not None else None
                    welford_ucl_disp_val = ucl_welford_disp[col_idx] if ucl_welford_disp is not None else None
                    welford_lcl_disp_val = lcl_welford_disp[col_idx] if lcl_welford_disp is not None else None

                    # 종합 이상치
                    raw_out_comb = bool(out_raw[col_idx] or out_raw_disp[col_idx])
                    fft_out_comb = bool(out_fft[col_idx] or out_fft_disp[col_idx])
                    kalman_out_comb = bool(out_kalman[col_idx] or out_kalman_disp[col_idx])

                    # ── 엑셀 행 구성 ──
                    row_dict: dict = {'일련번호': chunk_seq}
                    if group_cols:
                        for g in group_cols:
                            row_dict[g] = current_group_val[group_cols.index(g)] if current_group_val else None

                    for i in range(args.n):
                        row_dict[f'값{i+1}'] = raw_vals_padded[i]

                    row_dict['Raw_평균'] = raw_mean_vals[col_idx]
                    row_dict['Raw_변동'] = raw_disp_vals[col_idx]
                    row_dict['FFT_평균'] = fft_mean_vals[col_idx]
                    row_dict['FFT_변동'] = fft_disp_vals[col_idx]
                    row_dict['Kalman_평균'] = kalman_mean_vals[col_idx]
                    row_dict['Kalman_변동'] = kalman_disp_vals[col_idx]
                    
                    row_dict['상한_평균(선택기준)'] = basis_ucl
                    row_dict['하한_평균(선택기준)'] = basis_lcl
                    row_dict['상한_변동(선택기준)'] = basis_ucl_disp
                    row_dict['하한_변동(선택기준)'] = basis_lcl_disp
                    
                    row_dict['상한_평균(Welford)'] = welford_ucl_val
                    row_dict['하한_평균(Welford)'] = welford_lcl_val
                    row_dict['상한_변동(Welford)'] = welford_ucl_disp_val
                    row_dict['하한_변동(Welford)'] = welford_lcl_disp_val
                    
                    row_dict['Outlier_Raw_평균'] = bool(out_raw[col_idx])
                    row_dict['Outlier_Raw_변동'] = bool(out_raw_disp[col_idx])
                    row_dict['종합_Outlier_Raw'] = raw_out_comb

                    row_dict['Outlier_FFT_평균'] = bool(out_fft[col_idx])
                    row_dict['Outlier_FFT_변동'] = bool(out_fft_disp[col_idx])
                    row_dict['종합_Outlier_FFT'] = fft_out_comb

                    row_dict['Outlier_Kalman_평균'] = bool(out_kalman[col_idx])
                    row_dict['Outlier_Kalman_변동'] = bool(out_kalman_disp[col_idx])
                    row_dict['종합_Outlier_Kalman'] = kalman_out_comb
                    
                    row_dict['Baseline_Mean'] = b_mean[col_idx] if b_mean is not None else None
                    row_dict['Baseline_Disp'] = b_disp[col_idx] if b_disp is not None else None
                    row_dict['Mean_Shift'] = bool(mean_shift[col_idx]) if mean_shift is not None else False
                    row_dict['Variance_Spike'] = bool(var_spike[col_idx]) if var_spike is not None else False

                    excel_results[col].append(row_dict)

                    # ── PDF용 결과 저장 ──
                    group_str = str(current_group_val) if group_cols and current_group_val else None
                    all_results.append({
                        'chunk_idx': chunk_seq,
                        'column': col,
                        'group': group_str,
                        
                        # 평균 데이터
                        'raw': raw_mean_vals[col_idx],
                        'fft': fft_mean_vals[col_idx],
                        'kalman': kalman_mean_vals[col_idx],
                        'basis_val': basis_mean_val,
                        'ucl': basis_ucl,
                        'lcl': basis_lcl,
                        'is_outlier': basis_out,
                        'ucl_welford': welford_ucl_val,
                        'lcl_welford': welford_lcl_val,

                        # 변동 데이터
                        'raw_disp': raw_disp_vals[col_idx],
                        'fft_disp': fft_disp_vals[col_idx],
                        'kalman_disp': kalman_disp_vals[col_idx],
                        'basis_disp_val': basis_disp_val,
                        'ucl_disp': basis_ucl_disp,
                        'lcl_disp': basis_lcl_disp,
                        'is_outlier_disp': basis_out_disp,
                        'ucl_welford_disp': welford_ucl_disp_val,
                        'lcl_welford_disp': welford_lcl_disp_val,
                        
                        # 종합
                        'is_outlier_comb': bool(basis_out or basis_out_disp),
                        
                        # Baseline 및 Shift 데이터
                        'Baseline_Mean': b_mean[col_idx] if b_mean is not None else np.nan,
                        'Baseline_Disp': b_disp[col_idx] if b_disp is not None else np.nan,
                        'Mean_Shift': bool(mean_shift[col_idx]) if mean_shift is not None else False,
                        'Variance_Spike': bool(var_spike[col_idx]) if var_spike is not None else False
                    })

                    # ── 실시간 차트 데이터 업데이트 ──
                    if col in current_lines:
                        ld = current_lines[col]
                        ld['x_data'].append(chunk_seq)
                        ld['raw_y'].append(raw_mean_vals[col_idx])
                        ld['fft_y'].append(fft_mean_vals[col_idx])
                        ld['kalman_y'].append(kalman_mean_vals[col_idx])
                        ld['ucl_y'].append(basis_ucl if basis_ucl is not None else np.nan)
                        ld['lcl_y'].append(basis_lcl if basis_lcl is not None else np.nan)
                        ld['ucl_welford_y'].append(welford_ucl_val if welford_ucl_val is not None else np.nan)
                        ld['lcl_welford_y'].append(welford_lcl_val if welford_lcl_val is not None else np.nan)
                        
                        ld['baseline_y'].append(b_mean[col_idx] if b_mean is not None else np.nan)

                        if basis_out:
                            ld['outlier_x'].append(chunk_seq)
                            ld['outlier_y'].append(basis_mean_val)
                            
                        if mean_shift is not None and mean_shift[col_idx]:
                            ld['mean_shift_x'].append(chunk_seq)

                        # 변동 데이터 업데이트
                        ld['raw_disp_y'].append(raw_disp_vals[col_idx])
                        ld['fft_disp_y'].append(fft_disp_vals[col_idx])
                        ld['kalman_disp_y'].append(kalman_disp_vals[col_idx])
                        ld['ucl_disp_y'].append(basis_ucl_disp if basis_ucl_disp is not None else np.nan)
                        ld['lcl_disp_y'].append(basis_lcl_disp if basis_lcl_disp is not None else np.nan)
                        ld['ucl_welford_disp_y'].append(welford_ucl_disp_val if welford_ucl_disp_val is not None else np.nan)
                        ld['lcl_welford_disp_y'].append(welford_lcl_disp_val if welford_lcl_disp_val is not None else np.nan)

                        ld['baseline_disp_y'].append(b_disp[col_idx] if b_disp is not None else np.nan)

                        if basis_out_disp:
                            ld['outlier_disp_x'].append(chunk_seq)
                            ld['outlier_disp_y'].append(basis_disp_val)
                            
                        if var_spike is not None and var_spike[col_idx]:
                            ld['var_spike_x'].append(chunk_seq)

                    # ── n=1일 때 이전 값 업데이트 ──
                    last_vals_mean[col]['Raw'] = raw_mean_vals[col_idx]
                    last_vals_mean[col]['FFT'] = fft_mean_vals[col_idx]
                    last_vals_mean[col]['Kalman'] = kalman_mean_vals[col_idx]

                group_chunk_count += 1
                chunk_seq += 1

                # ── 현재 그룹 창 갱신 ──
                update_plot(current_lines, current_figs, target_cols, display_limit)
                plt.pause(args.t)
    except KeyboardInterrupt:
        logger.info("\n사용자에 의해 실행이 중단되었습니다. 중간 결과를 저장합니다.")

    plt.ioff()

    if not all_results:
        logger.warning("처리된 결과가 없습니다.")
        return

    logger.info("모든 데이터 처리 완료. 최종 리포트를 생성합니다.")
    results_df = pd.DataFrame(all_results)

    output_dir = './output'
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    base_filename = os.path.splitext(os.path.basename(selected_file))[0]

    # ── 엑셀 저장 (분석 칼럼이 2개 이상이면 파일 분리) ──
    save_excel(excel_results, target_cols, args.n, basis, output_dir, timestamp, base_filename)

    # ── 단일 PDF 저장 (그룹 × 칼럼 조합별로 페이지 생성) ──
    pdf_filename = f"{timestamp}_{base_filename}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)

    with PdfPages(pdf_path) as pdf:
        if group_cols:
            groups = results_df['group'].dropna().unique()
            for grp in groups:
                grp_data = results_df[results_df['group'] == grp]
                for col in target_cols:
                    col_data = grp_data[grp_data['column'] == col].sort_values('chunk_idx')
                    if col_data.empty:
                        continue
                    plot_and_save_pdf(pdf, col_data, col, grp, basis, args.n)
        else:
            for col in target_cols:
                col_data = results_df[results_df['column'] == col].sort_values('chunk_idx')
                if col_data.empty:
                    continue
                plot_and_save_pdf(pdf, col_data, col, None, basis, args.n)

    logger.info(f"결과 PDF 저장 완료: {pdf_path}")

    print("\n모든 작업이 완료되었습니다. 창을 닫으면 프로그램이 종료됩니다.")
    plt.show()


if __name__ == "__main__":
    main()
