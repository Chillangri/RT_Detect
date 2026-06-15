import pandas as pd
import logging
from typing import Iterator, Tuple, Optional, List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DataLoader:
    def __init__(self, file_path: str, n_samples: int = 4, group_cols: Optional[List[str]] = None, target_cols: Optional[List[str]] = None):
        """
        데이터 로더 초기화
        :param file_path: 분석할 데이터 파일 경로
        :param n_samples: 한 번에 취합할 표본 수 (n)
        :param group_cols: 통계 초기화의 기준이 되는 그룹핑 칼럼 리스트 (다중 가능)
        :param target_cols: 실제 분석을 진행할 타겟 숫자형 칼럼 리스트
        """
        self.file_path = file_path
        self.n_samples = n_samples
        self.group_cols = group_cols if group_cols else []
        self.target_cols = target_cols
        
    def load_data(self) -> pd.DataFrame:
        """
        선택된 단일 파일을 읽어 DataFrame으로 반환합니다.
        """
        try:
            if self.file_path.endswith('.csv'):
                df = pd.read_csv(self.file_path)
            else:
                df = pd.read_excel(self.file_path)
            logger.info(f"{self.file_path} 파일 로드 완료. (전체 형태: {df.shape})")
            
            # 필요한 칼럼들만 추출
            cols_to_keep = []
            
            if self.group_cols:
                cols_to_keep.extend([col for col in self.group_cols if col in df.columns])
            
            if self.target_cols:
                cols_to_keep.extend([col for col in self.target_cols if col in df.columns])
            else:
                # 타겟 칼럼이 명시되지 않으면 숫자형 전체 추출
                numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
                cols_to_keep.extend(numeric_cols)
                self.target_cols = numeric_cols

            # 중복 제거 (순서 유지)
            seen = set()
            cols_to_keep = [x for x in cols_to_keep if not (x in seen or seen.add(x))]

            return df[cols_to_keep]

        except Exception as e:
            logger.error(f"{self.file_path} 읽기 실패: {e}")
            return pd.DataFrame()

    def stream_data(self) -> Iterator[Tuple[int, pd.DataFrame]]:
        """
        로드된 데이터를 n_samples 크기로 나누어 스트리밍(Generator) 형태로 제공합니다.
        """
        df = self.load_data()
        if df.empty:
            logger.error("처리할 데이터가 없습니다.")
            return

        total_rows = len(df)
        for i in range(0, total_rows, self.n_samples):
            chunk = df.iloc[i:i + self.n_samples].copy()
            yield i, chunk
