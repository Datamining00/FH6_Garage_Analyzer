FH6 Assistant v1.4
=================

배포판별 실행 방법
------------------
Standard
- `FH6 Assistant v1.4.exe`를 실행합니다.

Portable
- `FH6 Assistant v1.4 Portable` 폴더를 유지한 상태에서 내부의 `FH6 Assistant v1.4.exe`를 실행합니다.

Source
- 압축을 쓰기 가능한 일반 폴더에 완전히 푼 뒤 `FH6 Assistant.vbs`를 실행합니다.
- 실행 문제가 있으면 `run.bat`으로 오류 내용을 확인할 수 있습니다.
- 최초 실행에서는 Python 환경과 필수 패키지 준비로 시간이 걸릴 수 있습니다.

백업
----
- 별도 백업 경로를 지정하지 않으면 FH6 Assistant의 LocalAppData 데이터 위치 아래 `backup` 폴더를 기본 저장소로 사용합니다.
- `외부에서 가져오기`는 다른 위치에 보관한 Livery/SoulBoundLivery 컨테이너를 분석하여 현재 백업 저장소 형식으로 정리합니다. 외부 원본은 삭제하지 않습니다.
- 백업 Import는 사용자 요청 시 검증된 백업 컨테이너를 게임 저장 구조에 복원합니다.
- `백업 후 원본 삭제`는 백업 데이터와 폴더 지문 검증이 성공한 일반 Livery에 한해 사용자 확인 후 게임 쪽 원본을 삭제할 수 있습니다.

데이터 안전성
------------
- 일반 세이브 스캔과 CacheThumbnails 분석은 읽기 전용입니다.
- 메모리 스캔은 OpenProcess의 읽기/조회 권한과 VirtualQueryEx, ReadProcessMemory만 사용하며 메모리 쓰기, 코드 주입, 후킹, 디버거 연결은 사용하지 않습니다.
- 게임 저장 파일 변경은 사용자가 명시적으로 실행한 백업 Import 또는 검증된 백업 후 원본 삭제 기능에서만 발생합니다.
- 설정·분류·분석 캐시·최근 변경 썸네일 복사본·마지막 메모리 스캔 결과는 LocalAppData의 FH6 Assistant 로컬 데이터 영역에 저장됩니다.

주의 사항
---------
- 압축 파일 내부에서 직접 실행하지 마십시오.
- Source 배포판에서는 app.py, run.bat, setup_and_run.ps1, requirements.txt, data 및 fh6garage 폴더를 서로 분리하거나 삭제하지 마십시오.
- 인게임 이동 기능은 Windows 키 입력을 FH6 창으로 전달하며 게임 프로세스 메모리를 수정하지 않습니다.

메모리 구현 참고
---------------
현재 메모리 스캔 구현은 공개된 Win32 API와 관찰된 FH6 런타임 레코드 형식을 기반으로 별도로 작성되었습니다. 공개 커뮤니티 연구인 Hx-zh/fh6-livery-viewer (AGPL-3.0)의 기능적 관찰 결과와 교차 확인했지만 해당 프로젝트의 소스 코드를 포함·임포트·링크하지 않습니다.

비공식 도구 안내
---------------
이 프로그램은 비공식 커뮤니티 도구이며 Microsoft, Xbox Game Studios, Playground Games 또는 Forza와 제휴하거나 보증받지 않았습니다.
