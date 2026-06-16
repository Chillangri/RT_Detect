# 참고자료
- 최초 프로그램 기획 : [[rt_detect 프로그램 기획서 (Gemini)]], [[01_RT_Detect Design (초안)]]
- 실시간 관리 상/하한 설정: [[관리 상한, 하한 설정 방법의 설계]]
- 이론적 배경: [[2203_Realtime_detect]], [[Welford Control Limits]], [[FFT와 Kalman의 UCL과 LCL]]

# 실시간 설비 데이터 분석 및 이상 탐지 파이프라인 (RT Detect)

이 프로그램은 향후 HearIM-Detect의 기반이 될 것으로, 현장에서 실시간으로 발생하는 센서 및 설비 데이터를 실시간으로 수집·분석하는 환경을 전제로 한다. 해당 환경에서 ① 데이터의 수집 주기($t$)와 분석 단위($n$, 샘플군의 수)를 설정하고, ② 수집 데이터를 대상으로 **실시간**으로 Noise를 제거하고 (Raw Data, FFT, Kalman Filter), ③ 평균 이동(Mean Shift)과 분산 폭증 (Variance Spike)을 판별하는 기능을 수행한다.

현재는 가상 데이터(Excel/CSV) 모사를 통한 알고리즘 검증 및 파이프라인 기반으로 구현되어 있으며, 향후 4개의 전문 Agent 기반 아키텍처로 확장 설계되었습니다.

## 🎯 프로젝트 개요 (Project Definition)

- **타겟 사용자 (Who)**: 생산 라인 작업자, 공정 제어 담당자, 품질 관리(QC) 엔지니어
- **해결 과제 (What)**: 복잡한 연산으로 인한 시스템 부하를 최소화하면서, 방대한 센서 데이터 속에서 실시간으로 이상치(Outlier)를 탐지하고 특정 Lot의 공정 조건 일치 여부를 판별
- **적용 환경 (Where)**: 진동, 주파수, 전류 센서 및 PLC가 연동되어 실시간 데이터가 발생하는 제조 현장 (예: 롤 타입 필름 제조 공정 등)
- **핵심 가치 (Why)**: 공정의 우연 원인에 의한 변동을 통제하고 일관된 조업 조건을 유지함으로써, 궁극적으로 흔들림 없는 핵심 품질 특성(CTQ, Critical-to-Quality)을 확보

---

## 🚀 주요 기능 (현재 구현 상태)

- **대화형(Interactive) 설정 및 동적 데이터 로딩**: `./source` 디렉토리에 위치한 Excel/CSV 파일을 읽어 지정된 주기($t$)와 크기($n$)에 맞춰 청크 단위로 스트리밍하며, CLI를 통해 분석 대상 파일, 타겟/그룹 칼럼 및 EWA 계산에 필요한 $\alpha$(가중치) 등 각종 파라미터를 설정하고 프로그램의 기동
- **다중 필터 기반 노이즈 제거 (FFT & Kalman)**: `apply_filters()` 함수를 통해 노이즈를 제거합니다.
  - **FFT Filter**: `scipy.fft`를 활용하여 최근 1만 개의 개별 측정값 히스토리에 대해 푸리에 변환 후 고주파(파라미터 `cutoff_ratio=0.5`) 대역을 차단하는 방식으로 필터링을 수행합니다.
  - **Kalman Filter**: 개별 측정값 스트림에 대해 예측 및 보정 단계를 거칩니다. `process_variance=1e-3`, `measurement_variance=1e-1` 파라미터를 사용하여 최적 추정치를 실시간 산출합니다.
- **지수 가중 이동 평균(EWMA) 기반 동적 한계선(3-Sigma)**: Welford 방식 대신 EWMA 방식을 도입하여 시간이 지나도 최신 데이터 트렌드에 대한 변별력(Sensitivity)을 잃지 않습니다. 사용자가 입력한 $\alpha$ 값 공식을 적용해 매 청크마다 프로세스 대평균과 분산을 동적으로 업데이트합니다.
- **초기 무시 청크 활용 통계 초기화**: 초기 설정한 개수(최소 2개)만큼의 부분군은 이상치 탐지에서 무시(`add_init_data()`)한 후, 해당 구간이 종료되면 모인 데이터로 초기 프로세스 분산과 평균을 셋팅(`finalize_init()`)하여 정확도를 높입니다.
- **이상치 탐지 및 실시간 시각화 / 강제 중단 지원**: 산출된 상/하한선을 벗어나는 데이터를 이상치로 마킹하고, Lot별로 실시간 트렌드 차트를 그립니다. 중간에 `Ctrl+C`로 중단하더라도 현재까지의 차트(PDF) 및 통계치(Excel)를 `./output` 폴더에 안전하게 저장합니다.

---
## 📶 주요 필터 (FFT vs. Kalman) 비교
FFT와 Kalman Filter는 신호/시계열 데이터를 다루는 대표적인 알고리즘이지만, 목적과 동작 방식이 근본적으로 다릅니다. FFT는 **주파수 영역 분석**, Kalman Filter는 **시간 영역 상태 추정**에 특화되어 있습니다.

### 핵심 개념 비교

| 항목         | FFT (Fast Fourier Transform) | Kalman Filter                                                                                                                                                                                  |
| ---------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **목적**     | 시간 도메인 → 주파수 도메인 변환          | 노이즈 포함 측정값으로 시스템 상태 추정                                                                                                                                                                         |
| **처리 방식**  | 비재귀적, 배치(Batch) 처리           | 재귀적(Recursive) 처리                                                                                                                                                                              |
| **입력**     | 등간격 샘플링된 시계열 신호              | 노이즈 포함 측정값 + 시스템 모델                                                                                                                                                                            |
| **출력**     | 주파수별 진폭/위상 스펙트럼              | 현재 상태 추정값 + 오차 공분산                                                                                                                                                                             |
| **시간 정보**  | 시간 정보 손실 (기본 DFT 기준)         | 시간 순서 유지, 이전 상태 활용                                                                                                                                                                             |
| **확률 모델**  | 없음 (결정론적 변환)                 | 가우시안 분포 기반 확률적 추정 [[taeyoung96.github](https://taeyoung96.github.io/slam/SLAM_07/)]                                                                                                            |
| **실시간 처리** | 어려움 (윈도우 필요)                 | 가능 (매 스텝 업데이트) [[developer-wh.tistory](https://developer-wh.tistory.com/entry/SORT-%EA%B5%AC%ED%98%84%EC%9D%84-%EC%9C%84%ED%95%9C-%EA%B8%B0%EC%B4%88-%EC%9D%B4%EB%A1%A0-3-feat-Kalman-filter)] |
| **수학적 기반** | 이산 푸리에 변환(DFT)               | Bayes Filter의 선형 특수 케이스 [[taeyoung96.github](https://taeyoung96.github.io/slam/SLAM_07/)]                                                                                                      |
| **가정 조건**  | 신호의 주기성 또는 유한 구간             | 선형 시스템 + 가우시안 노이즈 [[ko.wikipedia](https://ko.wikipedia.org/wiki/%EC%B9%BC%EB%A7%8C_%ED%95%84%ED%84%B0)]                                                                                        |
| **계산 복잡도** | O(N log N)                   | O(n³) (상태 차원 n에 비례)                                                                                                                                                                            |

### 공통점

- 둘 다 **노이즈가 포함된 시계열 신호** 처리에 사용됨[[einfochips](https://www.einfochips.com/jp/blog/fault-detection-using-a-bank-of-kalman-filters-and-a-fast-fourier-transform/)]
    
- **신호 처리(Signal Processing)** 분야의 핵심 도구
    
- 제조, 진동 분석, 항공우주 등 **임베디드/에지 컴퓨팅** 환경에서 함께 사용되는 경우가 많음[[einfochips](https://www.einfochips.com/jp/blog/fault-detection-using-a-bank-of-kalman-filters-and-a-fast-fourier-transform/)]
    
- 실제로 **FFT로 주파수 분석 후, Kalman Filter로 상태 추정**하는 하이브리드 파이프라인이 고장 진단(FDI)에 활용됨[[einfochips](https://www.einfochips.com/jp/blog/fault-detection-using-a-bank-of-kalman-filters-and-a-fast-fourier-transform/)]
    

### 주요 적용 분야

| 분야         | FFT                   | Kalman Filter                                                                                  |
| ---------- | --------------------- | ---------------------------------------------------------------------------------------------- |
| **제조/진동**  | 기계 이상 진단, FFT 스펙트럼 분석 | 센서 퓨전, 진동 상태 추정                                                                                |
| **자율주행**   | 레이다 신호 분석             | GPS + IMU 융합, 위치 추적 [[velog](https://velog.io/@hzzz15/Kalman-Filter)]                          |
| **음향/오디오** | 음성 인식, 노이즈 제거 필터 설계   | 음성 신호 추적                                                                                       |
| **금융**     | 주기성 분석, 사이클 검출        | 주가 필터링, 시계열 스무딩 [[velog](https://velog.io/@hzzz15/Kalman-Filter)]                              |
| **로봇공학**   | 조인트 진동 주파수 분석         | 위치/속도 추정 [[ko.wikipedia](https://ko.wikipedia.org/wiki/%EC%B9%BC%EB%A7%8C_%ED%95%84%ED%84%B0)] |
| **항공우주**   | 레이다 신호 처리             | 고도/속도/위치 추적 [[velog](https://velog.io/@hzzz15/Kalman-Filter)]                                  |
| **의료/바이오** | ECG/EEG 주파수 분석        | 생체신호 노이즈 제거                                                                                    |

### Python 함수 및 주요 파라미터

#### FFT — `numpy.fft` / `scipy.fft`

| 함수                     | 파라미터                               | 설명                 |
| ---------------------- | ---------------------------------- | ------------------ |
| `np.fft.fft(x)`        | `x`: 입력 배열, `n`: FFT 길이, `axis`: 축 | 1D 복소 FFT          |
| `np.fft.rfft(x)`       | 위와 동일                              | 실수 입력 전용 (절반 스펙트럼) |
| `np.fft.fftfreq(n, d)` | `n`: 샘플 수, `d`: 샘플 간격(1/샘플링 주파수)   | 주파수 축 생성           |
| **`scipy.fft.fft(x)`** | `workers=-1`로 병렬 처리 가능             | scipy 버전 (속도 우수)   |
| `np.fft.ifft(X)`       | `X`: 주파수 도메인 배열                    | 역변환 (복원)           |

```python
from scipy.fft import rfft, irfft, rfftfreq

signal = history[:, col_idx]  # 최대 10,000개 히스토리 데이터
W = rfft(signal)
freqs = rfftfreq(len(signal))
cutoff_freq = freqs.max() * cutoff_ratio  # 예: 0.5
W[freqs > cutoff_freq] = 0  # 고주파 차단
filtered = irfft(W, n=len(signal))
fft_result = filtered[-chunk_len:]
```

#### Kalman Filter — `filterpy` / `pykalman`

|파라미터|의미|비고|
|---|---|---|
|`F` (또는 `A`)|상태 전이 행렬|시스템 동적 모델 [[geeksforgeeks](https://www.geeksforgeeks.org/python/kalman-filter-in-python/)]|
|`H`|관측 행렬|상태 → 측정값 매핑 [[geeksforgeeks](https://www.geeksforgeeks.org/python/kalman-filter-in-python/)]|
|`Q`|프로세스 노이즈 공분산|모델 불확실성 [[wikidocs](https://wikidocs.net/336316)]|
|`R`|측정 노이즈 공분산|센서 오차 크기 [[wikidocs](https://wikidocs.net/336316)]|
|`P` (또는 `P0`)|초기 오차 공분산|초기 불확실성 [[geeksforgeeks](https://www.geeksforgeeks.org/python/kalman-filter-in-python/)]|
|`x0`|초기 상태 벡터|초기 추정값 [[geeksforgeeks](https://www.geeksforgeeks.org/python/kalman-filter-in-python/)]|
|`B`|제어 입력 행렬|외부 제어가 없으면 생략 [[geeksforgeeks](https://www.geeksforgeeks.org/python/kalman-filter-in-python/)]|


```python
# algorithm.py 내 자체 구현 1D Kalman Filter
process_variance, measurement_variance = 1e-3, 1e-1

# 이전 추정 상태 (est: 추정값, err: 추정 오차)
est, err = self.kf_state.get(col_idx, (val, 1.0))

# 1. 예측 (Predict)
priori_est = est
priori_err = err + process_variance

# 2. 교정 (Update)
K = priori_err / (priori_err + measurement_variance)  # 칼만 이득
est = priori_est + K * (val - priori_est)
err = (1 - K) * priori_err

self.kf_state[col_idx] = (est, err)
```


### 변형(Variants) 분류

|구분|FFT 계열|Kalman Filter 계열|
|---|---|---|
|**기본형**|DFT → FFT (Cooley-Tukey 알고리즘)|Linear Kalman Filter|
|**비선형 확장**|STFT (Short-Time FT, 시간-주파수 동시 분석)|Extended KF (EKF), Unscented KF (UKF)|
|**고급형**|Wavelet Transform (다해상도)|Particle Filter (비가우시안)|
|**실시간 최적화**|Sliding Window FFT|Fast Kalman Filter (FKF) [[ko.wikipedia](https://ko.wikipedia.org/wiki/%EA%B3%A0%EC%86%8D_%EC%B9%BC%EB%A7%8C_%ED%95%84%ED%84%B0)]|

**제조 진동 분석**이나 **센서 데이터 퓨전** 연구에서는 FFT로 지배 주파수를 찾고, 그 주파수 성분을 Kalman Filter의 상태 공간 모델에 반영하는 방식이 가장 강력한 접근법입니다.[[einfochips](https://www.einfochips.com/jp/blog/fault-detection-using-a-bank-of-kalman-filters-and-a-fast-fourier-transform/)]

---


## 🛠️ 함수 단위 수행 절차 (Execution Flow)

데이터 파이프라인의 핵심 로직은 다음과 같은 순서로 실행됩니다.

1. **`interactive_setup()`**: CLI를 통해 소스 파일, 그룹(Lot) 칼럼, 타겟 칼럼, $\alpha$ 값(기본 0.15), 초기 무시 청크 수(`ignore_init`, 최소 2), 차트 출력 기준(Raw/FFT/Kalman)을 입력받습니다.
2. **`stream_data()`**: `DataLoader` 인스턴스가 파일에서 데이터를 크기 $n$개 단위로 쪼개어 실시간 데이터(청크)를 발생시킵니다.
3. **`apply_filters()`**: 수신된 원본 청크(`target_data`)에 대해 FFT 필터와 Kalman 필터를 동시 적용하여 각각 필터링된 배열을 산출합니다.
4. **초기 수집 기간 (`ignore_init` 도달 전)**:
   - **`add_init_data()`**: 이상치 평가 및 EWMA 갱신을 생략하고 들어오는 청크 데이터를 배열로 수집해 둡니다.
   - **`finalize_init()`**: `ignore_init`에 지정된 개수만큼 수집이 끝나면, 수집된 전체 데이터와 청크별 분산의 평균을 이용해 EWMA 초기 평균값과 분산값을 셋팅합니다.
5. **실시간 모니터링 기간 (`ignore_init` 통과 후)**:
   - **`update_stats()`**: 매 청크마다 평균과 분산을 구한 뒤 $Z_t = \alpha X_t + (1-\alpha) Z_{t-1}$ 등의 EWMA 공식을 통해 프로세스 대평균 및 분산을 실시간 업데이트합니다.
   - **`get_limits()`**: 갱신된 대평균 및 분산을 바탕으로 3-Sigma 기반 관리 상/하한선(UCL, LCL)을 도출합니다.
   - **`detect_outliers()`**: 청크 평균값이 UCL/LCL 범위를 벗어났는지 불리언 배열로 판별합니다.
6. **시각화 및 저장 루프**:
   - **`update_plot()`**: 새 데이터, 한계선, 이상치 정보를 화면 차트에 실시간 갱신합니다. (가시성을 위해 Raw Mean은 연회색, FFT/Kalman은 상위에 Z-order 표기)
   - 중단(Ctrl+C) 또는 종료 시, **`save_excel()`** 및 **`plot_and_save_pdf()`** 함수가 호출되어 결과물을 `./output` 폴더에 출력합니다.

---

## 🔬 분석 알고리즘 상세 (Algorithm Details)

현재 파이프라인에서 데이터를 처리하고 이상치를 판단하는 핵심 수학적, 통계적 로직은 다음과 같이 구현되어 있습니다.

### 1. 필터링 및 노이즈 제거 (FFT & Kalman Filter)
- **FFT 필터 (Fast Fourier Transform)**
  - 개별 센서 데이터의 일정 크기(최대 10,000개 이력) 버퍼를 대상으로 `scipy.fft` 모듈을 사용해 주파수 대역으로 변환합니다.
  - 파라미터 `cutoff_ratio = 0.5`를 기본으로 적용하여 고주파 대역(노이즈) 신호를 차단(0으로 치환)한 뒤, `ifft`를 통해 다시 시간 도메인으로 복원합니다.
- **Kalman 필터 (Kalman Filter)**
  - 재귀적인(Recursive) 예측 및 교정 과정을 통해 실시간 신호의 참값을 추정합니다.
  - 파라미터 설정: 프로세스 노이즈 분산(`process_variance` $Q$) $= 1 \times 10^{-3}$, 측정 노이즈 분산(`measurement_variance` $R$) $= 1 \times 10^{-1}$로 설정되어 있으며, 각 측정마다 오차 공분산을 지속적으로 갱신하여 평활화된 값을 반환합니다.

### 2. Chunk 단위 데이터 활용 (Chunk Utilization)
- 실시간으로 스트리밍되는 데이터는 수집 주기($t$)와 묶음 크기($n$)에 따라 하나의 Chunk(부분군)로 묶여 처리됩니다.
- 각 Chunk 내에서 평균($\bar{X}$)과 변동(Range, $s$, 혹은 Moving Range)을 계산하며, 전체 히스토리를 재계산할 필요 없이 이전 단계의 추정값(State)과 현재의 Chunk 데이터만을 이용하여 통계량을 갱신하므로 연산 부하가 최소화됩니다.

### 3. 통계치 재귀적(Recursive) 갱신 및 관리한계(UCL/LCL) 산출
전체 히스토리를 메모리에 유지하며 재계산하는 방식은 스트리밍 환경에서 부하가 큽니다. 따라서 이전 상태(State)와 현재의 데이터(Chunk)만을 이용해 평균과 분산을 갱신하는 **재귀적(Recursive) 알고리즘**을 도입했습니다.

- **EWMA (지수 가중 이동 평균) 재귀 갱신**
  - **수식**: $Z_t = \alpha \cdot X_t + (1 - \alpha) \cdot Z_{t-1}$
  - 과거 데이터 비중을 지수적으로 감소시켜 최신 트렌드 반영력을 높입니다.
  
- **Welford 알고리즘 기반 누적 통계 재귀 갱신**
  - 전체 누적 평균과 누적 변동 평균을 메모리 오버플로우 없이 O(1) 시간복잡도로 안전하게 업데이트합니다.

- **UCL/LCL 관리 한계 계산**
  - 이렇게 재귀적으로 갱신된 대평균(Grand Mean)과 프로세스 분산(Dispersion)을 바탕으로 전통적인 SPC 계수표($d_2, A_2, A_3, B_3, B_4$ 등)를 적용하여 실시간으로 $\pm 3\sigma$ 한계선을 갱신합니다.

**💻 재귀적 업데이트 및 UCL/LCL 계산 로직 예시 (algorithm.py 발췌):**
```python
# 1. EWMA 재귀적 업데이트
# 현재 청크의 평균(chunk_mean)과 변동(chunk_disp)을 이전 EWMA 상태와 결합 (alpha: 가중치)
self.ewma_mean[basis] = self.alpha * chunk_mean + (1 - self.alpha) * self.ewma_mean[basis]
self.ewma_disp[basis] = self.alpha * chunk_disp + (1 - self.alpha) * self.ewma_disp[basis]

# 2. Welford 누적 평균/변동 재귀적 업데이트
self.welford_count += 1
self.welford_mean += (chunk_mean - self.welford_mean) / self.welford_count
self.welford_disp_mean += (chunk_disp - self.welford_disp_mean) / self.welford_count

# 3. 계산된 재귀 통계량을 바탕으로 실시간 UCL/LCL 산출 (부분군 크기 n에 따른 계수표 분기)
if 2 <= n <= 5:
    c = R_CHART_CONSTANTS[n]
    A2, D3, D4 = c["A2"], c["D3"], c["D4"]
    
    # 평균(X-bar) 관리한계선 (EWMA 기준)
    ucl_mean = self.ewma_mean[basis] + A2 * self.ewma_disp[basis]
    lcl_mean = self.ewma_mean[basis] - A2 * self.ewma_disp[basis]
    
    # 변동(R) 관리한계선
    ucl_disp = D4 * self.ewma_disp[basis]
    lcl_disp = D3 * self.ewma_disp[basis]
```

### 4. 기저선(Baseline) 추적 및 Shift/Spike 판정 기준
안정적인 공정 상태를 묘사하는 동적 기저선을 추적하여, 공정의 급격한 수준 변화(Mean Shift)나 변동 폭발(Variance Spike)을 감지합니다.

- **Baseline 산정 (Dynamic Baseline)**
  - `baseline_size` (기본 30개) 만큼의 윈도우 크기를 갖는 `deque` 버퍼를 운영합니다.
  - **정상 데이터 조건**: 새롭게 들어온 Chunk가 기존 관리 한계(UCL/LCL)를 벗어난 **Outlier가 아닌 경우에만** 이 기저선 버퍼에 추가됩니다.
  - 이 버퍼에 담긴 정상 데이터들의 평균과 변동 평균이 현재 공정의 `Baseline Mean`과 `Baseline Disp` (회색 실선)으로 사용됩니다.
- **Mean Shift (평균의 급격한 이동)**
  - 산출된 `Baseline Mean`과 `Baseline Disp`를 바탕으로, 표본 수($n$)에 따른 SPC 계수표를 적용하여 **기저선 기준의 UCL/LCL(즉, $\pm 3\sigma$)**을 계산합니다.
  - 평활화된 EWMA 대평균이 이 기저선 UCL을 상회하거나 LCL을 하회할 경우, 평균 수준에 심각한 Shift가 발생한 것으로 간주하여 붉은색 수직선 및 일련번호로 마킹합니다.
- **Variance Spike (변동폭 스파이크)**
  - 해당 시점 Chunk의 실제 변동값($MR, R,$ 또는 $s$)이 기저 변동(`Baseline Disp`)의 **3배(3.0배)를 초과**하는 경우, 순간적인 분산 폭발(Variance Spike)로 판정합니다.
  - 발생 시, 분산 차트상에 푸른색 수직선과 일련번호를 표기하고 엑셀에도 푸른색 폰트로 강조합니다.
- **예외 처리**: 기저선 버퍼가 가득 차기 전(초기 `baseline_size` 도달 전)에는 신뢰도 확보를 위해 Shift 및 Spike 감지를 일시적으로 억제합니다.

### 5. 시각화 및 결과 저장 로직 (Shift & Spike 마킹)
실시간으로 감지된 공정의 이상 상태(Mean Shift 및 Variance Spike)는 즉각적인 인지가 가능하도록 차트 및 엑셀 결과물에 시각적으로 강조됩니다.

- **실시간 차트 및 PDF 리포트 (`plot_and_save_pdf`, `update_plot`)**
  - **붉은색 세로선 (Mean Shift)**: 평균 관리도(상단 차트)에서 `Mean_Shift == True`인 Chunk 인덱스 위치에 붉은색 수직선(`vlines`)을 긋고, 상단에 해당 일련번호를 붉은 텍스트로 표기합니다.
  - **푸른색 세로선 (Variance Spike)**: 변동 관리도(하단 차트)에서 `Variance_Spike == True`인 Chunk 인덱스 위치에 푸른색 수직선(`vlines`)을 긋고, 상단에 해당 일련번호를 푸른 텍스트로 표기합니다.
- **Excel 데이터 저장 (`save_excel`)**
  - `openpyxl` 엔진을 사용하여 각 행(Row) 단위로 조건부 포맷팅(폰트 색상)을 적용합니다.
  - **Mean Shift 단독 발생**: 해당 데이터 행 전체를 **붉은색 굵은 폰트(Red Bold)**로 표기.
  - **Variance Spike 단독 발생**: 해당 데이터 행 전체를 **푸른색 굵은 폰트(Blue Bold)**로 표기.
  - **동시 발생 (Shift & Spike)**: 두 가지 이상이 동시에 발생한 심각한 상태로 간주하여 행 전체를 **보라색 굵은 폰트(Purple Bold)**로 표기합니다.
---

## 🧩 시스템 아키텍처 및 Agent 구성 (기획안)

이 시스템은 데이터 수집부터 시각화까지 데이터의 흐름에 따라 유기적으로 동작해야 하며, 이를 위해 총 4개의 특화된 Agent 구성으로 기획되었습니다.

| Agent 명칭 | 핵심 역할 | 주요 기술 스택 / 산출물 (예정 포함) |
| --- | --- | --- |
| **Data Pipeline Agent** | 다중 Source 연결 및 실시간 데이터 수집 | minimalmodbus (센서), snap7 (PLC), Excel 스트리밍 |
| **Algorithm Agent** | 신호 노이즈 제거 및 실시간 이상 탐지 로직 구현 | FFT Filter, Kalman Filter, Recursive Calculation 로직 (현재 구현 완료) |
| **Backend/DB Agent** | 데이터 파이프라인 관리 및 영구/실시간 저장소 운용 | PostgreSQL, Redis, REST/WebSocket API |
| **Frontend/UX Agent** | 실시간 트렌드 차트 및 UI/UX 시각화 | React/Vue, 웹 기반 대시보드 |

- **Data Pipeline Agent**: 물리적 센서(가속도, 진동 등)나 PLC, 또는 가상 데이터(Excel)로부터 지정된 주기와 표본 수에 맞추어 안정적으로 데이터를 추출합니다.
- **Algorithm Agent**: 유입된 데이터에 FFT/Kalman 필터를 적용하고, 전체 데이터 셋이 아닌 직전 값과 최근 획득한 데이터만을 사용하는 재귀적 방식으로 실시간 상하한선을 산출합니다. 또한 Lot 단위로 작업 조건이 동일하게 유지되는지 검증합니다.
- **Backend/DB Agent**: PostgreSQL(Batch Insert)에 데이터를 안전하게 영구 보존하고, Redis Stream 기반 Pub/Sub 구조를 마련하여 프론트엔드의 실시간 차트 렌더링을 돕습니다.
- **Frontend/UX Agent**: X축을 시간, Y축을 센서 측정값으로 하는 실시간 시계열 차트를 렌더링하고, 이상치 탐지 시 시각적 경고 및 특정 Lot 간 비교 뷰어를 제공합니다.

---

## 📁 디렉토리 구조

```text
RT_Detect/
├── source/               # 입력 데이터 폴더 (여기에 .csv, .xlsx 파일을 넣으세요)
├── output/               # 결과 출력 폴더 (PDF 리포트 및 엑셀 파일이 생성됩니다)
├── data_loader.py        # 데이터 스트리밍 및 로드 모듈
├── algorithm.py          # FFT/Kalman 필터 및 Recursive 3-Sigma 이상 탐지 모듈
├── main.py               # 파이프라인 메인 실행 컨트롤러 (Interactive 환경 지원)
├── run_pipeline.sh       # 파이프라인 구동용 쉘 스크립트
└── README.md             # 프로젝트 설명서 (현재 파일)
```


---

## ⚙️ 실행 방법

기본적으로 제공되는 쉘 스크립트(`run_pipeline.sh`)를 사용하여 간편하게 실행할 수 있습니다.
실행 시 `-t` (수집 주기, 초) 와 `-n` (한 번에 묶을 표본 수) 파라미터를 인자로 넘겨줄 수 있습니다. 
기본값은 $t=0.5$, $n=4$로 설정되어 있습니다.

### 1. 필수 패키지 설치
Python 3.x 환경에서 다음 패키지가 설치되어 있어야 합니다.

```bash
pip install pandas scipy numpy matplotlib openpyxl
```

### 2. 샘플 데이터 배치
`./source` 폴더 안에 테스트할 숫자형 데이터가 포함된 `.csv` 또는 `.xlsx` 파일을 넣어주세요.

### 3. 파이프라인 실행
터미널에서 아래 명령을 실행합니다.

```bash
# 기본 파라미터 (t=0.5, n=4) 로 실행
./run_pipeline.sh

# 커스텀 파라미터 지정 (예: t=1.0초, n=10개)
./run_pipeline.sh -t 1.0 -n 10
```

실행 후 터미널 창에 나타나는 안내에 따라 **분석할 파일 선택, Grouping(Lot) 기준 칼럼, 분석 대상 데이터 칼럼, EWMA 업데이트용 $\alpha$ 값, 초기 무시할 청크 개수(최소 2), 이상치 판정 기준(Raw/FFT/Kalman)**을 대화형으로 입력하시면 실시간 차트가 구동됩니다. (중간에 강제 종료를 원할 경우 `Ctrl+C`를 누르면 중단된 지점까지의 결과가 자동 저장됩니다.)

- 사용 변수명과 설정값 예시:
  t=0.1s, n=10, ignore_init=2, display_limit=300, basis=FFT, alpha=0.15, baseline_size=30)

```bash
./run_pipeline.sh -t 0.1 -n 10
==================================================
 실시간 설비 데이터 수집 및 이상 탐지 파이프라인 시작
 수집 주기(t) = 0.1 초, 표본 수(n) = 10 개
==================================================

[ 분석 대상 파일 선택 ]
  1. (확인)210906_검증내용.xlsx
  2. 1024_final (1).csv
  3. 1024_sensor7_3sigma (3).csv
  4. Result.xlsx
  5. YCCMonitoring.xlsx
  6. preprocessed_data0912(symbolic).csv
  7. sample_data.csv
파일 번호를 선택하세요 (1~7): 7

[ 칼럼 목록 ]
  1. sensor_id
  2. time
  3. value
  4. upper_limit
  5. lower_limit
  6. outlier_status

Grouping 기준이 되는 칼럼 번호를 선택하세요 (복수일 경우 쉼표로 구분, 없으면 0 입력): 1

분석 대상이 되는 데이터 칼럼 번호를 선택하세요 (복수일 경우 쉼표로 구분): 3

EWMA 평균/분산 업데이트에 사용할 alpha 값을 입력하세요 (기본 0.15): 

각 그룹별 초기 무시할 부분군(Chunk) 수를 입력하세요 (최소 2, 기본 2): 

한 화면에 표시할 최대 점(부분군 평균) 개수를 입력하세요 (기본 300): 

이상치 판정 기준을 선택하세요 (1: Raw, 2: FFT, 3: Kalman) [기본 2]: 2

기저선(Baseline) 산정에 필요한 데이터 숫자를 입력하세요 (기본 30): 

```
### 4. 결과 확인
파이프라인 실행이 완료된 후 창을 닫으면, `./output` 폴더에 분석 결과 파일이 생성됩니다.
- **PDF 파일 (`.pdf`)**: 원본 데이터, FFT/Kalman 필터링된 데이터, 상하한선(UCL/LCL) 밴드, 이상치 탐지 지점이 표시된 그룹/타겟별 시계열 차트가 포함되어 있습니다.
  붉은색 세로선은 평균 이동(Mean Shift), 푸른색 세로선은 분산 증가(Variance Spike)을 의미함.
- **Excel 파일 (`.xlsx`)**: 각 청크 단위로 기록된 원본 값, 필터링 평균값, 계산된 상/하한 수치 및 이상치 판정 여부 상세 데이터가 저장됩니다.
![[Img/SampleChart.png]]