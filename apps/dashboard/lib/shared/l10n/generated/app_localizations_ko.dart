import 'app_localizations.dart';

/// The translations for Korean (`ko`).
class SKo extends S {
  SKo([super.locale = 'ko']);

  @override
  String get appTitle => '신비재팬 대시보드';
  @override
  String get tabHome => '홈';
  @override
  String get tabInventory => '재고';
  @override
  String get tabTasks => '작업';
  @override
  String get tabWiki => '위키';
  @override
  String get tabSettings => '설정';
  @override
  String get loginTitle => '신비재팬에 로그인';
  @override
  String get loginWithSSO => '로그인';
  @override
  String loginError(String error) => '로그인 실패: $error';
  @override
  String get loginDomainHint => 'your-domain.com 계정으로 로그인해 주세요';
  @override
  String get logout => '로그아웃';
  @override
  String get search => '검색';
  @override
  String get loading => '로딩 중...';
  @override
  String get error => '오류';
  @override
  String get retry => '재시도';
  @override
  String get noResults => '결과 없음';
  @override
  String get parts => '부품';
  @override
  String get partCategories => '부품 카테고리';
  @override
  String get stock => '재고';
  @override
  String get stockLocations => '재고 위치';
  @override
  String get purchaseOrders => '구매 주문';
  @override
  String get salesOrders => '판매 주문';
  @override
  String get waybill => '운송장';
  @override
  String get projects => '프로젝트';
  @override
  String get tasks => '작업';
  @override
  String get kanban => '칸반';
  @override
  String get calendar => '캘린더';
  @override
  String get documents => '문서';
  @override
  String get collections => '컬렉션';
  @override
  String get newDocument => '새 문서';
  @override
  String get editDocument => '문서 편집';
  @override
  String get save => '저장';
  @override
  String get cancel => '취소';
  @override
  String get delete => '삭제';
  @override
  String get confirmDelete => '정말 삭제하시겠습니까?';
  @override
  String get settingsTitle => '설정';
  @override
  String get settingsLanguage => '언어';
  @override
  String get settingsTheme => '테마';
  @override
  String get themeDark => '다크';
  @override
  String get themeLight => '라이트';
  @override
  String get themeSystem => '시스템';
  @override
  String get settingsAbout => '정보';
  @override
  String get phoneManagement => '전화 관리';
  @override
  String get phoneUsers => '사용자';
  @override
  String get phoneDevices => '디바이스';
  @override
  String get phoneExtension => '내선 번호';
  @override
  String get phoneName => '이름';
  @override
  String get phonePassword => '비밀번호';
  @override
  String get phoneAddUser => '사용자 추가';
  @override
  String get customizeDashboard => '대시보드 커스터마이즈';
  @override
  String get resetDefaults => '초기화';
  @override
  String get voiceRequest => '음성 요청';
  @override
  String get voiceTargetEmail => '수신자 이메일';
  @override
  String get voiceTapToRecord => '탭하여 녹음';
  @override
  String get voiceRecording => '녹음 중...';
  @override
  String get voiceStart => '녹음 시작';
  @override
  String get voiceStop => '녹음 중지';
  @override
  String get voicePreviewTitle => '요청 내용 미리보기';
  @override
  String get voiceTaskTitle => '작업 제목';
  @override
  String get voiceDescription => '설명';
  @override
  String get voiceDueDate => '기한';
  @override
  String get voiceConfirm => '작업 생성';
  @override
  String get callRequest => '통화 요청';
  @override
  String get callCallerExtension => '내 내선 번호';
  @override
  String get callTargetExtension => '통화 대상 내선 번호';
  @override
  String get callStart => '발신';
  @override
  String get callRinging => '호출 중...';
  @override
  String get callInProgress => '통화 중';
  @override
  String get callAnalyze => '통화 분석';
  @override
  String get callAnalyzing => '분석 중...';
  @override
  String get callReady => '발신 준비 완료';
  @override
  String get callAnalysisResult => '통화 분석 결과';
  @override
  String get rakutenKeyManagement => '라쿠텐 API 키 관리';
  @override
  String get rakutenInstructions => '갱신 절차';
  @override
  String get rakutenStep1 => '1. RMS에 로그인';
  @override
  String get rakutenStep2 => '2. API 키 관리 페이지 열기';
  @override
  String get rakutenStep3 => '3. 새 키를 복사하여 아래에 붙여넣기';
  @override
  String get rakutenSubmitKeys => '새 키 제출';
  @override
  String get rakutenSubmit => '제출';
  @override
  String get rakutenStatusOk => '정상';
  @override
  String get rakutenStatusWarning => '갱신 권장';
  @override
  String get rakutenStatusExpired => '만료됨';
  @override
  String get rakutenStatusUnknown => '미설정';
  @override
  String get rakutenRenewedAt => '최종 갱신일';
  @override
  String get rakutenAgeDays => '경과 일수';
  @override
  String get rakutenDaysRemaining => '잔여 일수';
  @override
  String get pickingList => '피킹 리스트';
  @override
  String get pickingOrder => '피킹 주문';
  @override
  String get pickingSelectAll => '전체 선택';
  @override
  String get pickingScanHint => '바코드 스캔...';
  @override
  String get pickingScanProduct => '상품 바코드 스캔...';
  @override
  String get pickingNoOrders => '출하 대기 주문이 없습니다';
  @override
  String get pickingNoItems => '아이템이 없습니다';
  @override
  String get pickingNoOrder => '주문을 찾을 수 없습니다';
  @override
  String get pickingGenerateId => 'ID 생성';
  @override
  String get pickingPrintLabel => '라벨 인쇄';
  @override
  String get pickingStartBatch => '일괄 피킹';
  @override
  String get pickingBatchMode => '일괄 피킹';
  @override
  String get pickingCustomer => '고객';
  @override
  String get pickingItems => '건';
  @override
  String get pickingComplete => '피킹 완료';
  @override
  String get pickingCompletePick => '완료';
  @override
  String get pickingSplitToOrders => '주문별 분할';
  @override
  String get pickingSplitScanOrder => '주문 바코드 스캔';
  @override
  String get pickingSplitScanProduct => '상품 바코드 스캔';
  @override
  String get pickingSplitActive => '선택된 주문';
  @override
  String get pickingSplitSwitch => '주문 전환';
  @override
  String get pickingSplitAssigned => '할당됨';
  @override
  String get pickingSplitConfirm => '분할 확정';
  @override
  String get pickingSplitConfirmed => '분할이 확정되었습니다';
  @override
  String get pickingLabelPreview => '라벨 미리보기';
  @override
  String get pickingPrintHint => 'Ctrl+P로 브라우저 인쇄 대화상자를 열어주세요';
  @override
  String get pbxManagement => 'PBX 관리';
  @override
  String get pbxExtensions => '내선';
  @override
  String get pbxDayNight => '주야 모드';
  @override
  String get pbxRoutes => '라우트';
  @override
  String get pbxStatus => '상태';
  @override
  String get pbxAddExtension => '내선 추가';
  @override
  String get pbxDayMode => '주간 모드';
  @override
  String get pbxNightMode => '야간 모드';
  @override
  String get pbxOutboundRoutes => '발신 라우트';
  @override
  String get pbxInboundRoutes => '착신 라우트';
  @override
  String get pbxUptime => '가동 시간';
  @override
  String get pbxChannels => '채널';
  @override
  String get pbxEndpointsRegistered => '등록된 내선';
  @override
  String get pbxEndpointsTotal => '총 내선 수';
  @override
  String get pbxReload => '설정 다시 로드';
  @override
  String get pbxReloaded => 'PBX 설정이 다시 로드되었습니다';
  @override
  String get staffManagement => '직원 관리';
  @override
  String get staffDetail => '직원 상세';
  @override
  String get staffAdd => '직원 추가';
  @override
  String get staffEmail => '이메일';
  @override
  String get staffName => '표시 이름';
  @override
  String get staffRole => '역할';
  @override
  String get staffPermissions => '권한';
  @override
  String get staffPermissionsHint => '모든 권한은 기본적으로 ON입니다. OFF로 전환하여 제한합니다.';
  @override
  String get staffGuaranteedByRole => '역할에 의해 보장됨';
  @override
  String get staffSuperuserAllAccess => '슈퍼유저는 모든 기능에 접근할 수 있습니다.';
  @override
  String get staffDeleteConfirm => '이 직원을 삭제하시겠습니까?';
}
