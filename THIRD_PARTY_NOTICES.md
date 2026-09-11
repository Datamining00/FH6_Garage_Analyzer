# FH6 Assistant v1.5 — 오픈소스 및 라이선스

이 앱은 PySide6/Qt, Shiboken, Pillow, NumPy, PyOpenGL 및 아래 외부 구성요소를 사용합니다. 외부 구성요소는 각각의 저작권자와 라이선스에 따릅니다. 이 문서는 앱 전체에 MIT/GPL/AGPL 라이선스를 부여하지 않습니다. 라이브러리 소스 및 교체 안내는 SOURCE_AND_RELINKING.md에 있습니다.

## 앱 실행에 포함된 라이브러리

- Python 3.12.14: Python Software Foundation 및 원문에 기재된 기여자. Python 라이선스는 licenses/Python-LICENSE.txt.
- PySide6 / Qt / Shiboken 6.11.2: The Qt Company 및 해당 소스의 기여자. 이 배포는 해당 LGPLv3 허용 모듈을 LGPLv3 조건으로 사용합니다. licenses/qt에는 공식 소스의 라이선스와 하위 고지를 보존했습니다. 모듈별 INDEX.json으로 원래 파일 경로를 확인할 수 있습니다. Qt Virtual Keyboard는 이 보완 빌드에서 제외됩니다.
- Pillow 12.3.0: MIT-CMU 및 원문에 기재된 하위 구성요소 조건.
- NumPy 2.5.3: BSD-3-Clause 등 원문에 명시된 복수 라이선스.
- PyOpenGL 3.1.10: 각 원문 고지의 조건. 동봉된 freeglut 및 gle 등에도 개별 고지가 적용됩니다.
- PyInstaller 6.22.2: GPLv2-or-later와 부트로더/패키징 예외. PyInstaller 사용만으로 이 앱 전체를 GPL로 지정하지 않습니다.

라이브러리 원문 고지는 licenses/python 및 licenses/qt에 있습니다. Qt 소스에서 함께 수집한 예제·도구·선택적 구성요소의 고지는 해당 코드에 적용되며, 모든 소스 구성요소가 이 실행 파일에 포함되었다는 뜻은 아닙니다.

## KFPS 렌더러와 차량 변환기

프로젝트: heyitshestia/kloudys-forza-painter-suite
고정 커밋: 6f53ca3c584d78659d06d4b4a39561db67d79345
원본: https://github.com/heyitshestia/kloudys-forza-painter-suite/tree/6f53ca3c584d78659d06d4b4a39561db67d79345

- 원본 MIT 및 custom importer 고지: licenses/KFPS-LICENSE.txt, licenses/KFPS-custom-importer-LICENSE.txt. 원문에 있는 이전 프로젝트·저작권자 표기를 그대로 보존합니다.
- 렌더러의 필요한 부분은 첫 사용 시 다운로드됩니다. 중첩 그룹 해석, skew 조건, 캔버스 제한, raster 검색의 FH6 호환성 수정이 적용됩니다. 이 수정은 FH6 Assistant 측 변경이며 원저자의 변경으로 표시하지 않습니다.
- 동봉된 Kfps.ChassisConverter.WheelMorph.exe는 KFPS 기반 수정 변환기입니다. 휠 morph, 변환 체인 진단, 재질·텍스처·UV4 처리 및 Durango 보호 검사가 추가되었습니다. 해당 패치와 C# 파일은 소스 ZIP의 tools/kfps_wheel_morph 및 관련 patch 도구에 있습니다.
- 원본 KFPS는 ForzaLiveryStudio의 공개 연구·문서를 참고했다고 명시합니다. 그 사실만으로 ForzaLiveryStudio 코드가 포함됐다고 표시하지 않습니다.

## 변환기에 포함된 ForzaTechStudio 및 .NET

KFPS 변환기는 ForzaTechStudio ModelImporter, ForzaTools.Bundles, ForzaTools.Shared, DurangoTypes 코드를 사용합니다. MIT 원문 및 Copyright (c) 2023 Nenkai 표기는 licenses/ForzaTechStudio-vendor-LICENSE.txt에 보존됩니다. 앱에서 별도로 참고한 4f373c5fb192551ce5249e320dd79b1399b693ca 버전의 원문은 licenses/ForzaTechStudio-reference-LICENSE.txt입니다.

변환기의 .NET 런타임 및 Microsoft.Extensions.Logging, Syroot.BinaryData 원문과 .NET 하위 고지는 licenses/converter에 있습니다. 앱은 게임 개발사나 이 외부 프로젝트의 공식 제품이 아닙니다.

## 데이터·구조·수식 참고 — 권한 확인과 구분

- HDR: 차량 ID/차량명 데이터와 튜닝 구조 문서. https://gist.github.com/HDR/0659d1717bc61504bf83750628963f4f 및 https://gist.github.com/HDR/41426137a24ef83b3f391542ce51982d
- Dr-hydra/FH6-Adjust-Tool 25cfd00195e74f8a85180b5f3193ee105259e2e2: 휠 사양 SQLite DB 다운로드 및 구조 참고. 해당 host/QING.Core는 AGPL-3.0-only. DB 자체의 권리까지 이 코드 라이선스로 보장하지 않습니다.
- Doliman100/ForzaTech-extraction-tools d126767b4a63f4fdaa2143c4983f08a8c9974802: 휠/타이어 수식·구조 참고. 원본 프로젝트는 GPL-3.0. 수식/형식 참고와 코드 복제의 법적 범위는 구분해야 하며, 이 표시만으로 앱 전체를 GPL로 바꾸거나 이용 권한을 새로 부여하지 않습니다.

이 자료들의 사용 범위 및 미확인 권리는 DATA_PROVENANCE_REVIEW.md에 기록했습니다. 감사용 라이선스 수집과 출처 표기만으로 모든 자료의 재배포 허가가 확보된 것은 아닙니다.
