# WSL 개발 환경과 저장 공간

개발 도구 설치 위치·경로 공유·WSL 2의 용량 문제를 다룰 때 읽는다. 모든 개발·설치 작업에서 compact를 실행하라는 규칙은 아니다.
Windows 호스트, 배포판, 컨테이너 저장소를 먼저 구분한다. 실제 정리·종료·디스크 변경은 요청 범위와 영향을 확인한 뒤 진행한다.

## 설치 전에 경계 확인

- Windows와 WSL의 interpreter·패키지 관리자·에이전트 설정·로그인 저장소는 별개다. 어느 쪽에 설치하는지 명시한다.
- Linux 홈에 설치해도 WSL 2의 VHDX는 Windows 드라이브 공간을 사용한다. `/mnt/c`, `/mnt/d`의 파일은 Windows 파일이다.
- symlink·mount가 Windows 경로를 가리키면 Linux 폴더로 보이더라도 설치·삭제가 Windows 파일에 영향을 줄 수 있다.
  대상의 실제 경로를 확인하며, 경로 보호가 설치를 거절하면 제한을 끄지 말고 올바른 환경/대상을 선택한다.
- 개발 도구는 필요한 배포판·환경에만 설치하고, 캐시·빌드 산출물·컨테이너 데이터의 보관과 제거 범위를 정한다.

## 용량이 줄지 않을 때

| 관측 | 확인·다음 행동 |
|---|---|
| Linux 내부 사용량이 큼 | 해당 배포판에서 `df -h /`, `du -xhd1 "$HOME"` 등으로 원인을 좁힌다. 캐시·빌드·로그와 보존할 데이터를 구분한다. |
| 내부 파일 삭제 후에도 Windows 공간이 거의 그대로 | Linux의 빈 블록과 동적으로 확장된 VHDX의 실제 파일 크기는 다르다. 필요하면 지원되는 회수·compact 경로를 검토한다. |
| `/mnt/c`·`/mnt/d` 또는 외부 mount 사용량이 큼 | 해당 호스트 경로를 따로 조사한다. 배포판 정리나 삭제로 이 파일이 함께 제거된다고 가정하지 않는다. |
| Docker Desktop 저장소가 큼 | 배포판 VHD와 별개일 수 있다. Docker의 이미지·build cache·volume 보관 정책과 관리 화면을 확인한다. |

WSL 배포판 삭제는 용량 정리 명령이 아니다. `wsl --unregister`는 대상 배포판의 데이터를 삭제하므로
일반 정리·compact의 대안으로 실행하지 않는다. 삭제 후 남은 공간을 조사할 때도 다른 배포판·호스트 파일·별도 가상 디스크를 구분한다.

## 필요할 때만 compact

1. Windows에서 `wsl --version`, `wsl --list --verbose`, `wsl --help`로 대상 배포판·WSL 2 여부·지원 명령을 확인한다.
2. 배포판·실제 VHDX 위치·Windows 드라이브 여유 공간을 확인한다. 저장 위치를 AppData 등 고정 경로로 추측하지 않는다.
   [Microsoft의 VHD 경로 찾기](https://learn.microsoft.com/en-us/windows/wsl/disk-space#how-to-locate-the-vhdx-file-and-disk-path-for-your-linux-distribution)를 따른다.
3. 필요한 데이터를 백업하고 복구 가능성을 확인한다. 배포판 내부 정리도 삭제 대상·데이터 소유권을 먼저 검토한다.
4. WSL·Docker·DB·에이전트 작업을 저장·종료한다. `wsl --shutdown`은 모든 배포판과 실행 작업에 영향을 줄 수 있다. 종료가 기존 요청에 포함되는지 확인하고 승인 범위 밖의 진행 작업은 동의 없이 중단하지 않는다. WSL 안의 에이전트도 끊기므로 Windows 측 후속 확인과 재연결 계획을 먼저 확보한다.
5. 설치된 WSL 버전이 지원하는 회수 명령과 공식 문서를 우선 확인한다. `--resize`로 최대 용량을 바꾸는 것과 host 파일 compact는 구분한다.
6. 수동 DiskPart `compact vdisk`를 사용한다면 실제 동적 VHD를 선택해야 하며, 분리된 상태 또는 읽기 전용 연결 상태여야 한다.
   관리자 권한·백업·정확한 파일 선택이 필요하다. 다른 디스크의 명령을 복사하거나 사용 중인 VHD를 수정하지 않는다.
7. 실제 Windows 여유 공간, VHDX 크기, 배포판 재시작과 프로젝트·DB·컨테이너 동작을 다시 확인한다. 회수량은 조건에 따라 다르다.

에이전트는 진단 결과를 보고한 뒤 필요한 조치를 선택한다. 요청하지 않은 `prune --volumes`, 배포판 삭제,
디스크 연결·포맷·compact를 설치 후처리나 정기 작업으로 자동 실행하지 않는다.

## 공식 자료

확인일: 2026-11-20. 명령 지원과 제한은 사용 시 설치 버전의 도움말 및 최신 공지로 다시 확인한다.

- [WSL 디스크 공간과 VHDX 위치](https://learn.microsoft.com/en-us/windows/wsl/disk-space)
- [WSL 기본 명령·종료·내보내기·등록 해제](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
- [DiskPart compact vdisk의 조건](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/compact-vdisk)
