#!/bin/bash

# 기본값 설정
T_VAL=0.1
N_VAL=4

# 인자 파싱 (예: ./run_pipeline.sh -t 1.0 -n 10)
while getopts "t:n:" opt; do
  case ${opt} in
    t ) T_VAL=$OPTARG ;;
    n ) N_VAL=$OPTARG ;;
    \? ) echo "사용법: $0 [-t 수집주기(초)] [-n 표본수]"
         exit 1
         ;;
  esac
done

echo "=================================================="
echo " 실시간 설비 데이터 수집 및 이상 탐지 파이프라인 시작"
echo " 수집 주기(t) = $T_VAL 초, 표본 수(n) = $N_VAL 개"
echo "=================================================="

# ./source 폴더가 없으면 생성
mkdir -p source
# ./output 폴더가 없으면 생성
mkdir -p output

# 파이프라인 실행
python main.py --t "$T_VAL" --n "$N_VAL"

echo "=================================================="
echo " 처리가 완료되었습니다. ./output 폴더를 확인해 주세요."
echo "=================================================="
