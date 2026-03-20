import 'app_localizations.dart';

/// The translations for Japanese (`ja`).
class SJa extends S {
  SJa([super.locale = 'ja']);

  @override
  String get appTitle => 'シンビジャパン ダッシュボード';
  @override
  String get tabHome => 'ホーム';
  @override
  String get tabInventory => '在庫';
  @override
  String get tabTasks => 'タスク';
  @override
  String get tabWiki => 'Wiki';
  @override
  String get tabSettings => '設定';
  @override
  String get loginTitle => 'シンビジャパンにサインイン';
  @override
  String get loginWithSSO => 'サインイン';
  @override
  String loginError(String error) => 'サインインに失敗しました: $error';
  @override
  String get loginDomainHint => 'your-domain.com のアカウントでサインインしてください';
  @override
  String get logout => 'サインアウト';
  @override
  String get search => '検索';
  @override
  String get loading => '読み込み中...';
  @override
  String get error => 'エラー';
  @override
  String get retry => '再試行';
  @override
  String get noResults => '結果が見つかりません';
  @override
  String get parts => '部品';
  @override
  String get partCategories => '部品カテゴリ';
  @override
  String get stock => '在庫';
  @override
  String get stockLocations => '在庫ロケーション';
  @override
  String get purchaseOrders => '発注書';
  @override
  String get salesOrders => '受注書';
  @override
  String get waybill => '送り状';
  @override
  String get projects => 'プロジェクト';
  @override
  String get tasks => 'タスク';
  @override
  String get kanban => 'カンバン';
  @override
  String get calendar => 'カレンダー';
  @override
  String get documents => 'ドキュメント';
  @override
  String get collections => 'コレクション';
  @override
  String get newDocument => '新規ドキュメント';
  @override
  String get editDocument => 'ドキュメント編集';
  @override
  String get save => '保存';
  @override
  String get cancel => 'キャンセル';
  @override
  String get delete => '削除';
  @override
  String get confirmDelete => '本当に削除しますか？';
  @override
  String get settingsTitle => '設定';
  @override
  String get settingsLanguage => '言語';
  @override
  String get settingsTheme => 'テーマ';
  @override
  String get themeDark => 'ダーク';
  @override
  String get themeLight => 'ライト';
  @override
  String get themeSystem => 'システム';
  @override
  String get settingsAbout => 'バージョン情報';
  @override
  String get phoneManagement => '電話管理';
  @override
  String get phoneUsers => 'ユーザー';
  @override
  String get phoneDevices => 'デバイス';
  @override
  String get phoneExtension => '内線番号';
  @override
  String get phoneName => '名前';
  @override
  String get phonePassword => 'パスワード';
  @override
  String get phoneAddUser => 'ユーザー追加';
  @override
  String get customizeDashboard => 'ダッシュボードのカスタマイズ';
  @override
  String get resetDefaults => '初期化';
  @override
  String get voiceRequest => '音声依頼';
  @override
  String get voiceTargetEmail => '依頼先メールアドレス';
  @override
  String get voiceTapToRecord => 'タップして録音';
  @override
  String get voiceRecording => '録音中...';
  @override
  String get voiceStart => '録音開始';
  @override
  String get voiceStop => '録音停止';
  @override
  String get voicePreviewTitle => '依頼内容プレビュー';
  @override
  String get voiceTaskTitle => 'タスク名';
  @override
  String get voiceDescription => '説明';
  @override
  String get voiceDueDate => '期限';
  @override
  String get voiceConfirm => 'タスク作成';
  @override
  String get callRequest => '通話依頼';
  @override
  String get callCallerExtension => '自分の内線番号';
  @override
  String get callTargetExtension => '通話先内線番号';
  @override
  String get callStart => '発信';
  @override
  String get callRinging => '呼出中...';
  @override
  String get callInProgress => '通話中';
  @override
  String get callAnalyze => '通話分析';
  @override
  String get callAnalyzing => '分析中...';
  @override
  String get callReady => '発信準備完了';
  @override
  String get callAnalysisResult => '通話分析結果';
  @override
  String get rakutenKeyManagement => '楽天APIキー管理';
  @override
  String get rakutenInstructions => '更新手順';
  @override
  String get rakutenStep1 => '1. RMSにログイン';
  @override
  String get rakutenStep2 => '2. APIキー管理ページを開く';
  @override
  String get rakutenStep3 => '3. 新しいキーをコピーして下に貼り付け';
  @override
  String get rakutenSubmitKeys => '新しいキーを送信';
  @override
  String get rakutenSubmit => '送信';
  @override
  String get rakutenStatusOk => '正常';
  @override
  String get rakutenStatusWarning => '更新推奨';
  @override
  String get rakutenStatusExpired => '期限切れ';
  @override
  String get rakutenStatusUnknown => '未設定';
  @override
  String get rakutenRenewedAt => '最終更新日';
  @override
  String get rakutenAgeDays => '経過日数';
  @override
  String get rakutenDaysRemaining => '残日数';
  @override
  String get pickingList => 'ピッキングリスト';
  @override
  String get pickingOrder => 'ピッキング注文';
  @override
  String get pickingSelectAll => '全選択';
  @override
  String get pickingScanHint => 'バーコードをスキャン...';
  @override
  String get pickingScanProduct => '商品バーコードをスキャン...';
  @override
  String get pickingNoOrders => '出荷待ちの注文はありません';
  @override
  String get pickingNoItems => 'アイテムがありません';
  @override
  String get pickingNoOrder => '注文が見つかりません';
  @override
  String get pickingGenerateId => 'ID生成';
  @override
  String get pickingPrintLabel => 'ラベル印刷';
  @override
  String get pickingStartBatch => '一括ピッキング';
  @override
  String get pickingBatchMode => '一括ピッキング';
  @override
  String get pickingCustomer => '顧客';
  @override
  String get pickingItems => '点';
  @override
  String get pickingComplete => 'ピッキング完了';
  @override
  String get pickingCompletePick => '完了';
  @override
  String get pickingSplitToOrders => '注文に分割';
  @override
  String get pickingSplitScanOrder => '注文バーコードをスキャン';
  @override
  String get pickingSplitScanProduct => '商品バーコードをスキャン';
  @override
  String get pickingSplitActive => '選択中の注文';
  @override
  String get pickingSplitSwitch => '注文切替';
  @override
  String get pickingSplitAssigned => '割当済';
  @override
  String get pickingSplitConfirm => '分割確定';
  @override
  String get pickingSplitConfirmed => '分割が確定されました';
  @override
  String get pickingLabelPreview => 'ラベルプレビュー';
  @override
  String get pickingPrintHint => 'Ctrl+P でブラウザ印刷ダイアログを開いてください';
  @override
  String get pbxManagement => 'PBX管理';
  @override
  String get pbxExtensions => '内線';
  @override
  String get pbxDayNight => '昼夜モード';
  @override
  String get pbxRoutes => 'ルート';
  @override
  String get pbxStatus => '状態';
  @override
  String get pbxAddExtension => '内線追加';
  @override
  String get pbxDayMode => '昼間モード';
  @override
  String get pbxNightMode => '夜間モード';
  @override
  String get pbxOutboundRoutes => '発信ルート';
  @override
  String get pbxInboundRoutes => '着信ルート';
  @override
  String get pbxUptime => '稼働時間';
  @override
  String get pbxChannels => 'チャンネル';
  @override
  String get pbxEndpointsRegistered => '登録済み内線';
  @override
  String get pbxEndpointsTotal => '総内線数';
  @override
  String get pbxReload => '設定再読み込み';
  @override
  String get pbxReloaded => 'PBX設定を再読み込みしました';
  @override
  String get staffManagement => 'スタッフ管理';
  @override
  String get staffDetail => 'スタッフ詳細';
  @override
  String get staffAdd => 'スタッフ追加';
  @override
  String get staffEmail => 'メールアドレス';
  @override
  String get staffName => '表示名';
  @override
  String get staffRole => '役割';
  @override
  String get staffPermissions => '権限';
  @override
  String get staffPermissionsHint => 'すべての権限はデフォルトでONです。OFFにして制限します。';
  @override
  String get staffGuaranteedByRole => '役割により保証';
  @override
  String get staffSuperuserAllAccess => 'スーパーユーザーはすべての機能にアクセスできます。';
  @override
  String get staffDeleteConfirm => 'このスタッフを削除しますか？';
}
