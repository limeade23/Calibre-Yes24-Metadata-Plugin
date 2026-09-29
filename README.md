# Calibre Yes24 OpenAPI Metadata Source Plugin

Yes24 OpenAPI를 이용한 캘리버 국내도서 메타데이터 다운로드 플러그인


![실행 화면](https://github.com/user-attachments/assets/470f9332-4a5d-4cdc-a4da-0867ddd7116c)


## 설치 방법

1. 압축된 `Calibre-Yes24-Metadata-Plugin.zip` 파일을 받아 Calibre 환경설정 - 플러그인 - **파일에서 플러그인 불러오기**에서 플러그인을 등록한다.
2. [Yes24 Developers](https://developers.yes24.com/)에서 API Key를 발급받는다.
3. **플러그인 사용자 정의**에서 발급받은 **API Key**를 입력한다.
4. 메타데이터 편집하기에서 메타데이터 다운로드를 클릭하면 책 정보와 책 표지를 받아오게 된다.


![설정 화면](https://github.com/user-attachments/assets/21dc2cd9-9bbc-4f71-8a74-1dee4ecd6637)


### 참고사항

- calibre 9.15.0에서 테스트되었습니다.
- 검색 범위는 국내도서로 제한됩니다.
- 언어는 한국어로 고정되어 있습니다.
- ISBN10, ISBN13 및 Yes24 상품번호를 이용한 조회를 지원합니다.
- 제목, 저자, 출판사, 출간일, ISBN, 책 소개, 목차, 시리즈, 사용자 평점 및 표지를 가져옵니다.
- Yes24 기본키의 초당 호출 한도인 10회를 넘지 않도록 요청 속도를 제한합니다.
- 일일 호출 횟수는 별도로 카운트하거나 차단하지 않습니다.
