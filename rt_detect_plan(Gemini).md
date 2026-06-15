
실시간 설비 데이터 수집 및 이상 탐지 시스템(Real-time Outlier Detection System) 구축을 위한 프로젝트 기획서를 다음과 같이 작성.

효과적인 문제 정의와 시스템 구현을 위해, 타겟 사용자(Who), 해결 과제(What), 적용 환경(Where), 핵심 가치(Why)를 기반으로 프로젝트의 방향성을 명확히 하고, 이를 달성하기 위해 4개의 전문 Agent를 구성하여 업무를 분담했습니다.

# 📊 실시간 설비 데이터 분석 및 이상 탐지 시스템 기획서

## 1. 프로젝트 개요 (Project Definition)

- 타겟 사용자 (Who): 생산 라인 작업자, 공정 제어 담당자, 품질 관리(QC) 엔지니어
    
- 해결 과제 (What): 복잡한 연산으로 인한 시스템 부하를 최소화하면서, 방대한 센서 데이터 속에서 실시간으로 이상치(Outlier)를 탐지하고 특정 Lot의 공정 조건 일치 여부를 판별
    
- 적용 환경 (Where): 진동, 주파수, 전류 센서 및 PLC가 연동되어 실시간 데이터가 발생하는 제조 현장 (예: 롤 타입 필름 제조 공정 등)
    
- 핵심 가치 (Why): 공정의 우연 원인에 의한 변동을 통제하고 일관된 조업 조건을 유지함으로써, 궁극적으로 흔들림 없는 핵심 품질 특성(CTQ, Critical-to-Quality)을 확보
    

## 2. Agent 구성 및 역할 정의

이 시스템은 데이터 수집부터 시각화까지 데이터의 흐름에 따라 유기적으로 동작해야 합니다. 따라서 개발 및 운영을 총 4개의 특화된 Agent로 나누어 구성합니다.

| Agent 명칭            | 핵심 역할                        | 주요 기술 스택 / 산출물                                              |
| ------------------- | ---------------------------- | ----------------------------------------------------------- |
| Data Pipeline Agent | 다중 Source 연결 및 실시간 데이터 수집    | minimalmodbus, snap7, vibration.py, frequency_refactored.py |
| Algorithm Agent     | 신호 노이즈 제거 및 실시간 이상 탐지 로직 구현  | FFT Filter, Kalman Filter, Recursive Calculation 로직         |
| Backend/DB Agent    | 데이터 파이프라인 관리 및 영구/실시간 저장소 운용 | PostgreSQL, Redis, REST/WebSocket API                       |
| Frontend/UX Agent   | 실시간 트렌드 차트 및 UI/UX 시각화       | React/Vue (예상), 대시보드 화면 (SampleScreen.png 등)                |

## 3. Agent별 세부 수행 지시서 (Task Assignments)

### 👨‍💻 Agent 1: Data Pipeline Agent (데이터 수집 담당)

목표: 물리적 센서, PLC, 또는 가상 데이터(Excel)로부터 지정된 주기와 표본 수에 맞추어 안정적으로 데이터를 추출합니다.

- Task 1. 다중 Data Source 연동 인터페이스 구축:
    

- 유형 1 (실제 센서): minimalmodbus를 활용하여 RTU 프로토콜 기반의 가속도, 각속도, 진동 속도 데이터 수집 (vibration.py 참조).
    
- 유형 2 (PLC): snap7을 활용하여 PLC 메모리(랙/슬롯)에 직접 접근, 주파수(CV/SV) 및 전류 데이터 수집 (frequency_refactored.py 참조).
    
- 유형 3 (Excel): 시연 및 테스트를 위해 사전에 기록된 Excel 데이터를 선택하여 스트리밍하는 기능 구현.
    

- Task 2. 데이터 취합 주기(Sampling Rate) 로직 구현:
    

- 사용자가 설정한 데이터 취합 주기($t$)와 표본의 숫자($n$)를 바탕으로 버퍼링 로직을 구현합니다.
    
- 예: $n=3$, $t=0.3$으로 설정된 경우, 0.9초 동안 수집된 3개의 데이터의 평균값을 산출하여 Algorithm Agent로 전달합니다.
    

### 🧠 Agent 2: Algorithm Agent (신호 처리 및 이상 탐지 담당)

목표: 유입된 데이터의 노이즈를 제거하고, 시스템 부하를 최소화하는 방식으로 실시간 통계적 이상치를 탐지합니다.

- Task 1. 신호 전처리 (노이즈 제거):
    

- 제공된 분석 결과(FFTfilter_KALMANfilter.ipynb)에 따르면 FFT 필터가 Kalman 필터보다 RMSE 수치가 낮고 원본 데이터 보존 성능이 우수합니다.
    
- 따라서 센서 데이터(특히 진동 데이터) 수신 시 FFT(Fast Fourier Transform) 필터를 우선 적용하여 노이즈를 제거합니다.
    

- Task 2. 재귀적 연산(Recursive Calculation) 기반 동적 한계선 산출:
    

- 전체 데이터 셋을 매번 계산하는 대신, 직전 값과 최근 획득한 데이터만을 사용하는 재귀적 방식으로 평균(Mean)과 표준편차(Standard Deviation)를 연산합니다 (2203_Realtime_detect.md 논문 참조).
    
- 이를 통해 실시간 상한선(Upper Limit) 및 하한선(Lower Limit)을 동적으로 업데이트합니다. (예: 3-Sigma Rule 적용)
    

- Task 3. 이상치 판별 및 Lot 일관성 검증:
    

- 전처리된 실시간 값이 동적 상하한선을 벗어나는지(outlier_status) 판별합니다.
    
- Lot 단위로 데이터 분포를 비교하여, 서로 다른 Lot 간의 작업 조건이 동일하게 유지되고 있는지 검증하는 로직을 추가합니다.
    

### 🗄️ Agent 3: Backend/DB Agent (데이터베이스 및 API 담당)

목표: 실시간으로 발생하는 데이터를 지연 없이 처리하고, 분석 이력을 영구적으로 보존합니다.

- Task 1. 하이브리드 데이터베이스 시스템 구축:
    

- PostgreSQL (영구 저장): Batch Insert 방식을 사용하여 측정 시간, 센서 ID, 원본 값, 필터링 값, 상하한선, 이상치 여부를 RDB에 안전하게 로깅합니다.
    
- Redis (실시간 스트리밍): 프론트엔드의 실시간 차트 렌더링을 위해 Redis Stream을 활용하여 데이터를 메모리 기반으로 빠르게 캐싱하고 Pub/Sub 구조를 마련합니다.
    

- Task 2. 환경 설정 및 보안 관리:
    

- .env 파일을 통한 DB 접속 정보, PLC IP, Modbus 포트 분리 및 관리를 철저히 합니다.
    

- Task 3. API 서비스 계층 개발:
    

- Frontend Agent가 사용할 이력 조회 API(RESTful) 및 실시간 데이터 송출 API(WebSocket)를 구축합니다.
    

### 🎨 Agent 4: Frontend/UX Agent (시각화 및 UI 담당)

목표: 분석 결과를 작업자가 직관적으로 인지하고 즉각적인 조치를 취할 수 있도록 대시보드를 구성합니다.

- Task 1. 실시간 트렌드 차트 구현 (TrendChat_Lot1, TrendChat_Lot2 참조):
    

- X축을 시간, Y축을 센서 측정값으로 하는 실시간 시계열 차트를 렌더링합니다.
    
- 센서 원본 값, FFT 필터링 값이 차별화되게 표시되도록 구현합니다.
    
- 동적으로 변화하는 상한선(UCL)과 하한선(LCL)을 밴드 형태나 기준선으로 시각화하여 정상 범위를 한눈에 보여줍니다.
    

- Task 2. 이상치 경고 및 시스템 제어 UI (SampleScreen 참조):
    

- 이상치가 탐지될 경우 차트 상에 붉은색 점격 등으로 명확한 시각적 알림(Alert)을 제공합니다.
    
- 사용자가 Data Source(센서, PLC, Excel)를 선택하고 취합 주기($t$)와 표본 수($n$)를 설정할 수 있는 제어 패널(Control Panel)을 구성합니다.
    

- Task 3. Lot 비교 뷰어 제공:
    

- 특정 Lot 간의 트렌드를 겹쳐 보거나 나란히 비교할 수 있는 기능을 제공하여 CTQ 유지 여부를 확인할 수 있게 합니다.
    

**