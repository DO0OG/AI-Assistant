# Ari Voice Command(AI-Assistant)
> 음성 인식을 통한 데스크탑 기능 및 편의 기능 제어와 AI 모델을 이용한 대화 기능을 구현한 프로그램으로
>
> 기본적은 캐릭터 위젯은 shimeji와 유사하게 만들었습니다.

- 캐릭터 모델 제작 : [자라탕](https://github.com/yongmen20)

![image](https://github.com/user-attachments/assets/fc8de4b7-57ca-4c22-812c-e5dcc7b45cdd)

## 음성 명령어 목록

### 기본 명령어

- **"아리야"**: 음성 인식을 시작합니다.

### 웹 브라우저 관련 명령어

- **"[사이트 이름] 열어 줘"**: 지정된 사이트를 웹 브라우저로 엽니다.
  예: "네이버 열어 줘", "유튜브 열어 줘"

- **"유튜브 [검색어] 재생"**: 유튜브에서 검색어로 영상을 찾아 재생합니다.
  예: "유튜브 뉴스 재생"

- **"유튜브 [검색어] 검색"**: 유튜브에서 검색어로 검색 결과를 보여줍니다.
  예: "유튜브 요리 레시피 검색"

- **"[검색어] 검색해 줘"**: 구글에서 검색어를 검색합니다.
  예: "날씨 검색해 줘"

### 시스템 제어 명령어

- **"볼륨 키우기"** 또는 **"볼륨 올려"**: 시스템 볼륨을 높입니다.

- **"볼륨 줄이기"** 또는 **"볼륨 내려"**: 시스템 볼륨을 낮춥니다.

- **"음소거"**: 시스템 음소거를 켭니다.

- **"음소거 해제"**: 시스템 음소거를 해제합니다.

- **"[숫자]분 타이머"**: 지정된 시간으로 타이머를 설정합니다.
  예: "5분 타이머"

- **"타이머 취소"** 또는 **"타이머 끄기"** 또는 **"타이머 중지"**: 현재 실행 중인 타이머를 취소합니다.

- **"[숫자]분 뒤에 컴퓨터 꺼 줘"** 또는 **"[숫자]분 후에 컴퓨터 꺼 줘"**: 지정된 시간 후에 컴퓨터를 종료합니다.
  예: "30분 뒤에 컴퓨터 꺼 줘"

- **"전원 꺼 줘"** 또는 **"컴퓨터 꺼 줘"**: 컴퓨터를 즉시 종료합니다.

### 정보 요청 명령어

- **"몇 시야"**: 현재 시간을 알려줍니다.

- **"날씨 어때"**: 현재 위치의 날씨 정보를 알려줍니다.

### 기타 명령어

- 위 명령어들 외의 질문이나 요청은 AI 어시스턴트가 처리하여 응답합니다.

## 설정

### AI 모델
- 기본적으로 AI 모델은 [Bllossom](https://huggingface.co/MLP-KTLim/llama-3-Korean-Bllossom-8B-gguf-Q4_K_M)이 포함되어 있습니다.
- 다른 모델을 사용하길 원하면 사용자가 [HuggingFace](https://huggingface.co/)에서 gguf 모델을 받아 `models` 폴더에 넣어 사용해야 합니다.


## 의존성
- Python 3.11+
- [whisper](https://github.com/openai/whisper)
- [MeloTTS](https://github.com/myshell-ai/MeloTTS)
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- PySide6
- torch
- pvporcupine
- pyaudio
- requests
- geopy
- pydub
- webdriver_manager
- selenium
- psutil
- comtypes (Windows 전용)
- pycaw (Windows 전용)
- etc...

## 라이선스
- 이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 기여하기
- 버그 리포트, 기능 제안, 풀 리퀘스트 등 모든 형태의 기여를 환영합니다. 기여하기 전에 [CONTRIBUTING.md](CONTRIBUTING.md)를 읽어주세요.

## 연락처
- 프로젝트에 대한 질문이나 제안이 있으시면 [이슈](https://github.com/DO0OG/AI-Assistant/issues)를 열어주세요.
- 또는 이메일 mad_doggo@dogdev.buzz로 연락주세요.

