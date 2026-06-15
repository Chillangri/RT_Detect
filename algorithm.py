import numpy as np
from scipy.fft import rfft, irfft, rfftfreq
import scipy.special as sp

# R 관리도 계수표 (2 <= n <= 5)
# n=1인 경우 이동범위(MR)의 샘플 크기는 2이므로, n=2의 계수를 사용합니다.
R_CHART_CONSTANTS = {
    2: {"A2": 1.880, "D3": 0.0, "D4": 3.267, "d2": 1.128, "d3": 0.853},
    3: {"A2": 1.023, "D3": 0.0, "D4": 2.574, "d2": 1.693, "d3": 0.888},
    4: {"A2": 0.729, "D3": 0.0, "D4": 2.282, "d2": 2.059, "d3": 0.880},
    5: {"A2": 0.577, "D3": 0.0, "D4": 2.114, "d2": 2.326, "d3": 0.864},
}


def calculate_s_constants(n: int) -> tuple[float, float, float, float]:
    """s 관리도 계수(c4, A3, B3, B4) 동적 계산.

    Args:
        n: 부분군 크기 (n >= 6)

    Returns:
        (c4, A3, B3, B4) 계수 튜플
    """
    if n < 2:
        return 1.0, 3.0, 0.0, 0.0

    # gammaln을 사용하여 오버플로우 방지하며 c4 계산
    c4 = np.sqrt(2.0 / (n - 1)) * np.exp(sp.gammaln(n / 2.0) - sp.gammaln((n - 1) / 2.0))
    A3 = 3.0 / (c4 * np.sqrt(n))

    val = 1.0 - c4**2
    val = max(0.0, val)  # 수치적 음수 방지
    B3 = max(0.0, 1.0 - (3.0 / c4) * np.sqrt(val))
    B4 = 1.0 + (3.0 / c4) * np.sqrt(val)

    return c4, A3, B3, B4


class RTAlgorithm:
    """SPC X/X-bar 관리도 및 변동(MR/R/s) 관리도 기반 실시간 이상 탐지 알고리즘.

    핵심 설계:
    - Sample Size (n)에 따른 분기 로직 적용:
      - n = 1: Individual(X) & Moving Range(MR) 관리도
      - n = 2~5: X-bar & Range(R) 관리도
      - n >= 6: X-bar & Standard Deviation(s) 관리도
    - 지수 가중 이동 평균(EWMA)을 사용하여 프로세스 대평균과 평균 변동(Dispersion)을 추정
    - 초기 무시 부분군들을 이용하여 초기 대평균과 변동 평균을 산출
    - 관리도 작성을 위한 계수표(A2, d2, D4 등 및 동적 c4 계산)를 사용하여 UCL/LCL 산출
    - Raw, FFT, Kalman 3가지 방법론 각각에 대해 개별 측정값 역사와 통계(대평균, 변동 평균)를 추적
    """

    def __init__(self, n_subgroup: int = 4, alpha: float = 0.15, baseline_size: int = 30, selected_basis: str = 'FFT'):
        """
        Args:
            n_subgroup: 부분군 크기 (한 번에 묶는 표본 수)
            alpha: EWMA 업데이트에 사용되는 가중치 (0 < alpha <= 1)
            baseline_size: 기저선 산정에 유지할 정상 데이터 최대 개수
            selected_basis: 기저선 계산에 사용할 기준 (Raw, FFT, Kalman 중 택일)
        """
        self.n_subgroup = n_subgroup
        self.alpha = alpha
        self.baseline_size = baseline_size
        self.selected_basis = selected_basis
        self.reset()

    def reset(self):
        """통계치 전체 초기화 (그룹 변경 시 호출)."""
        self.bases = ['Raw', 'FFT', 'Kalman']
        
        # ── 초기 무시 구간 데이터 수집 버퍼 ──
        self.init_data = {b: [] for b in self.bases}

        # ── EWMA 기반 상태 변수 ──
        self.ewma_mean = {b: None for b in self.bases}
        self.ewma_disp = {b: None for b in self.bases}  # 분산 대신 변동(dispersion)의 EWMA 추적

        # ── n=1일 때 이전 시점 데이터 저장을 위한 상태 변수 ──
        self.last_val = {b: None for b in self.bases}

        # ── Welford 기반 상태 변수 (누적 평균 및 변동 추적용) ──
        self.welford_count = 0
        self.welford_mean = None
        self.welford_disp_mean = None
        self.last_raw_val = None

        # ── 필터 상태 (개별 데이터 스트림 대상) ──
        self.raw_individual_history: list[np.ndarray] = []
        self.kf_state: dict[int, tuple[float, float]] = {}

        # ── 기저선(Baseline) 상태 변수 ──
        from collections import deque
        self.baseline_mean_queues = {}
        self.baseline_disp_queues = {}

    # ────────────────────────────────────────────────
    # 필터 처리 (개별 데이터)
    # ────────────────────────────────────────────────

    def apply_filters(self, raw_chunk: np.ndarray, cutoff_ratio: float = 0.5):
        """
        입력된 Raw chunk(크기 n)에 대해 FFT와 Kalman 필터를 적용한 chunk를 반환.
        
        Returns:
            fft_chunk, kalman_chunk
        """
        chunk_len = len(raw_chunk)
        n_cols = raw_chunk.shape[1]
        
        # 1. Kalman Filter 적용
        kalman_chunk = np.zeros_like(raw_chunk, dtype=float)
        process_variance, measurement_variance = 1e-3, 1e-1
        
        for i in range(chunk_len):
            for col_idx in range(n_cols):
                val = float(raw_chunk[i, col_idx])
                if col_idx not in self.kf_state:
                    est, err = val, 1.0
                else:
                    est, err = self.kf_state[col_idx]

                priori_est = est
                priori_err = err + process_variance

                K = priori_err / (priori_err + measurement_variance)
                est = priori_est + K * (val - priori_est)
                err = (1 - K) * priori_err

                self.kf_state[col_idx] = (est, err)
                kalman_chunk[i, col_idx] = est

        # 2. FFT 적용 (히스토리에 기반)
        for i in range(chunk_len):
            self.raw_individual_history.append(raw_chunk[i])
            
        # 퍼포먼스를 위해 최대 10000개 유지
        if len(self.raw_individual_history) > 10000:
            self.raw_individual_history = self.raw_individual_history[-10000:]
            
        history = np.array(self.raw_individual_history)
        fft_chunk = np.zeros_like(raw_chunk, dtype=float)
        
        if len(history) < 2:
            fft_chunk = raw_chunk.copy()
        else:
            for col_idx in range(n_cols):
                signal = history[:, col_idx]
                W = rfft(signal)
                freqs = rfftfreq(len(signal))
                max_freq = freqs.max()
                cutoff_freq = max_freq * cutoff_ratio
                W[freqs > cutoff_freq] = 0
                filtered = irfft(W, n=len(signal))
                fft_chunk[:, col_idx] = filtered[-chunk_len:]
                
        return fft_chunk, kalman_chunk

    # ────────────────────────────────────────────────
    # 통계 업데이트 및 EWMA
    # ────────────────────────────────────────────────

    def add_init_data(self, basis: str, ind_chunk: np.ndarray):
        """초기 무시 구간 동안의 데이터를 수집."""
        self.init_data[basis].append(ind_chunk)

    def _calculate_chunk_disp(self, basis: str, ind_chunk: np.ndarray) -> np.ndarray:
        """주어진 청크 또는 개별 데이터에 대해 변동(MR, R, s) 계산."""
        n = self.n_subgroup
        n_cols = ind_chunk.shape[1]
        if n == 1:
            # n=1인 경우: 이동범위(MR). 이전 값이 없으면 0.
            if self.last_val[basis] is None:
                disp = np.zeros(n_cols, dtype=float)
            else:
                disp = np.abs(ind_chunk[0] - self.last_val[basis])
            return disp
        elif 2 <= n <= 5:
            # n=2~5인 경우: 범위(R).
            return np.max(ind_chunk, axis=0) - np.min(ind_chunk, axis=0)
        else:
            # n>=6인 경우: 표준편차(s).
            return np.std(ind_chunk, axis=0, ddof=1)

    def finalize_init(self, basis: str):
        """수집된 초기 데이터로 EWMA 초기 평균과 변동(disp) 계산."""
        if not self.init_data[basis]:
            return
            
        all_data = np.concatenate(self.init_data[basis], axis=0)
        self.ewma_mean[basis] = np.mean(all_data, axis=0)
        
        n = self.n_subgroup
        if n == 1:
            # n=1인 경우, 모든 수집된 데이터의 인접 값 간 MR의 평균을 계산
            if len(all_data) > 1:
                mrs = np.abs(np.diff(all_data, axis=0))
                self.ewma_disp[basis] = np.mean(mrs, axis=0)
            else:
                self.ewma_disp[basis] = np.zeros(all_data.shape[1])
            self.last_val[basis] = all_data[-1].copy()
        else:
            # n >= 2인 경우, 수집된 각 부분군(chunk)별 변동값의 산술평균을 초기 변동으로 지정
            chunk_disps = []
            for chunk in self.init_data[basis]:
                if len(chunk) > 0:
                    if n <= 5:
                        disp = np.max(chunk, axis=0) - np.min(chunk, axis=0)
                    else:
                        disp = np.std(chunk, axis=0, ddof=1) if len(chunk) > 1 else np.zeros(chunk.shape[1])
                    chunk_disps.append(disp)
            if chunk_disps:
                self.ewma_disp[basis] = np.mean(chunk_disps, axis=0)
            else:
                self.ewma_disp[basis] = np.zeros(all_data.shape[1])

    def update_stats(self, basis: str, ind_chunk: np.ndarray, chunk_mean: np.ndarray):
        """특정 basis(Raw/FFT/Kalman)의 평균과 변동(disp)을 EWMA로 업데이트."""
        chunk_disp = self._calculate_chunk_disp(basis, ind_chunk)

        # n=1일 때는 상태 변수 last_val 업데이트
        if self.n_subgroup == 1:
            self.last_val[basis] = ind_chunk[0].copy()

        if self.ewma_mean[basis] is None:
            self.ewma_mean[basis] = chunk_mean.copy()
            self.ewma_disp[basis] = chunk_disp.copy()
            return

        # 대평균 EWMA 갱신
        self.ewma_mean[basis] = self.alpha * chunk_mean + (1 - self.alpha) * self.ewma_mean[basis]
        
        # 변동 평균 EWMA 갱신
        self.ewma_disp[basis] = self.alpha * chunk_disp + (1 - self.alpha) * self.ewma_disp[basis]

    # ────────────────────────────────────────────────
    # 관리한계선 및 이상치 (UCL / LCL)
    # ────────────────────────────────────────────────

    def get_process_disp(self, basis: str) -> np.ndarray | None:
        """개별 측정값 또는 부분군의 평균 변동 (process dispersion)."""
        return self.ewma_disp[basis]

    def get_limits(self, basis: str, sigma_multiplier: float = 3.0):
        """SPC 관리도 한계선 쌍(평균 관리도 UCL/LCL, 변동 관리도 UCL/LCL) 산출.
        
        Returns:
            (ucl_mean, lcl_mean, ucl_disp, lcl_disp)
        """
        n = self.n_subgroup
        mean_val = self.ewma_mean[basis]
        disp_val = self.ewma_disp[basis]

        if mean_val is None or disp_val is None:
            return None, None, None, None

        if n == 1:
            # Individual & MR 관리도
            # n=2의 계수를 사용: d2=1.128, D3=0, D4=3.267
            d2 = R_CHART_CONSTANTS[2]["d2"]
            D3 = R_CHART_CONSTANTS[2]["D3"]
            D4 = R_CHART_CONSTANTS[2]["D4"]
            
            # X 차트 UCL/LCL
            ucl_mean = mean_val + 3.0 * (disp_val / d2)
            lcl_mean = mean_val - 3.0 * (disp_val / d2)
            
            # MR 차트 UCL/LCL
            ucl_disp = D4 * disp_val
            lcl_disp = D3 * disp_val
            
        elif 2 <= n <= 5:
            # Xbar-R 관리도
            c = R_CHART_CONSTANTS[n]
            A2, D3, D4 = c["A2"], c["D3"], c["D4"]
            
            ucl_mean = mean_val + A2 * disp_val
            lcl_mean = mean_val - A2 * disp_val
            
            ucl_disp = D4 * disp_val
            lcl_disp = D3 * disp_val
            
        else:
            # Xbar-s 관리도 (n >= 6)
            c4, A3, B3, B4 = calculate_s_constants(n)
            
            ucl_mean = mean_val + A3 * disp_val
            lcl_mean = mean_val - A3 * disp_val
            
            ucl_disp = B4 * disp_val
            lcl_disp = B3 * disp_val

        return ucl_mean, lcl_mean, ucl_disp, lcl_disp

    def detect_outliers(self, values: np.ndarray, ucl, lcl) -> np.ndarray:
        """값이 UCL/LCL 범위를 벗어나는지 판정."""
        if ucl is None or lcl is None:
            return np.zeros(len(values), dtype=bool)
        return (values > ucl) | (values < lcl)

    def update_welford(self, raw_chunk: np.ndarray):
        """Welford 알고리즘 구조를 모사하여, 누적 산술 평균과 누적 변동 평균 업데이트."""
        n_cols = raw_chunk.shape[1]
        n = self.n_subgroup

        # 평균 계산
        chunk_mean = np.mean(raw_chunk, axis=0)
        
        # 변동값 계산
        if n == 1:
            if self.last_raw_val is None:
                chunk_disp = np.zeros(n_cols, dtype=float)
            else:
                chunk_disp = np.abs(raw_chunk[0] - self.last_raw_val)
            self.last_raw_val = raw_chunk[0].copy()
        elif 2 <= n <= 5:
            chunk_disp = np.max(raw_chunk, axis=0) - np.min(raw_chunk, axis=0)
        else:
            chunk_disp = np.std(raw_chunk, axis=0, ddof=1)

        self.welford_count += 1

        if self.welford_mean is None:
            self.welford_mean = chunk_mean.copy()
            self.welford_disp_mean = chunk_disp.copy()
            return

        # 누적 평균 업데이트
        self.welford_mean += (chunk_mean - self.welford_mean) / self.welford_count
        # 누적 변동 평균 업데이트
        self.welford_disp_mean += (chunk_disp - self.welford_disp_mean) / self.welford_count

    def get_welford_limits(self, sigma_multiplier: float = 3.0):
        """Welford 누적 통계 기반 UCL/LCL 한계선 쌍(평균 및 변동) 산출."""
        n = self.n_subgroup
        mean_val = self.welford_mean
        disp_val = self.welford_disp_mean

        if mean_val is None or disp_val is None:
            return None, None, None, None

        if n == 1:
            d2 = R_CHART_CONSTANTS[2]["d2"]
            D3 = R_CHART_CONSTANTS[2]["D3"]
            D4 = R_CHART_CONSTANTS[2]["D4"]
            
            ucl_mean = mean_val + 3.0 * (disp_val / d2)
            lcl_mean = mean_val - 3.0 * (disp_val / d2)
            
            ucl_disp = D4 * disp_val
            lcl_disp = D3 * disp_val
            
        elif 2 <= n <= 5:
            c = R_CHART_CONSTANTS[n]
            A2, D3, D4 = c["A2"], c["D3"], c["D4"]
            
            ucl_mean = mean_val + A2 * disp_val
            lcl_mean = mean_val - A2 * disp_val
            
            ucl_disp = D4 * disp_val
            lcl_disp = D3 * disp_val
            
        else:
            c4, A3, B3, B4 = calculate_s_constants(n)
            
            ucl_mean = mean_val + A3 * disp_val
            lcl_mean = mean_val - A3 * disp_val
            
            ucl_disp = B4 * disp_val
            lcl_disp = B3 * disp_val

        return ucl_mean, lcl_mean, ucl_disp, lcl_disp

    def update_baseline(self, chunk_mean: np.ndarray, chunk_disp: np.ndarray, is_outlier: np.ndarray):
        """선택된 basis의 데이터를 기반으로 정상 데이터만 윈도우 큐에 추가하여 기저선을 갱신합니다."""
        from collections import deque
        n_cols = len(chunk_mean)
        if not self.baseline_mean_queues:
            for i in range(n_cols):
                self.baseline_mean_queues[i] = deque(maxlen=self.baseline_size)
                self.baseline_disp_queues[i] = deque(maxlen=self.baseline_size)
        
        for i in range(n_cols):
            if not is_outlier[i]:
                self.baseline_mean_queues[i].append(chunk_mean[i])
                self.baseline_disp_queues[i].append(chunk_disp[i])

    def get_baseline_stats(self) -> tuple[np.ndarray | None, np.ndarray | None]:
        """현재 버퍼에 있는 정상 데이터들의 기저 평균과 기저 변동 평균을 산출합니다."""
        n_cols = len(self.baseline_mean_queues)
        if n_cols == 0:
            return None, None
        
        b_mean = np.zeros(n_cols)
        b_disp = np.zeros(n_cols)
        
        for i in range(n_cols):
            if len(self.baseline_mean_queues[i]) > 0:
                b_mean[i] = np.mean(self.baseline_mean_queues[i])
                b_disp[i] = np.mean(self.baseline_disp_queues[i])
            else:
                b_mean[i] = np.nan
                b_disp[i] = np.nan
                
        return b_mean, b_disp

    def detect_shifts(self, b_mean: np.ndarray, b_disp: np.ndarray, ewma_mean: np.ndarray, ewma_disp: np.ndarray):
        """
        계수표를 적용한 Baseline 기반 UCL/LCL 대비 EWMA 평균이 벗어나면 Mean Shift,
        EWMA 변동이 기저 분산의 3배를 초과하면 Variance Spike로 판별합니다.
        """
        if b_mean is None or ewma_mean is None:
            return None, None, None, None
            
        n = self.n_subgroup
        n_cols = len(b_mean)
        
        ucl_mean = np.full(n_cols, np.nan)
        lcl_mean = np.full(n_cols, np.nan)
        mean_shift = np.zeros(n_cols, dtype=bool)
        var_spike = np.zeros(n_cols, dtype=bool)
        
        if np.isnan(b_mean).all():
            return mean_shift, var_spike, ucl_mean, lcl_mean
            
        if n == 1:
            d2 = R_CHART_CONSTANTS[2]["d2"]
            ucl_mean = b_mean + 3.0 * (b_disp / d2)
            lcl_mean = b_mean - 3.0 * (b_disp / d2)
        elif 2 <= n <= 5:
            c = R_CHART_CONSTANTS[n]
            A2 = c["A2"]
            ucl_mean = b_mean + A2 * b_disp
            lcl_mean = b_mean - A2 * b_disp
        else:
            c4, A3, B3, B4 = calculate_s_constants(n)
            ucl_mean = b_mean + A3 * b_disp
            lcl_mean = b_mean - A3 * b_disp
            
        # Mean Shift 판별
        mean_shift = (ewma_mean > ucl_mean) | (ewma_mean < lcl_mean)
        
        # Variance Spike 판별 (기저 변동의 3배 초과)
        var_spike = (ewma_disp > 3.0 * b_disp)
        
        # 기저선 데이터가 지정된 크기(baseline_size)에 도달하기 전에는 Shift/Spike를 감지하지 않음
        for i in range(n_cols):
            if len(self.baseline_mean_queues[i]) < self.baseline_size:
                mean_shift[i] = False
                var_spike[i] = False
        
        return mean_shift, var_spike, ucl_mean, lcl_mean
