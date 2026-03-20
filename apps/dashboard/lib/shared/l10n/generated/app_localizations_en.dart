import 'app_localizations.dart';

/// The translations for English (`en`).
class SEn extends S {
  SEn([super.locale = 'en']);

  @override
  String get appTitle => 'Shinbee Japan Dashboard';
  @override
  String get tabHome => 'Home';
  @override
  String get tabInventory => 'Inventory';
  @override
  String get tabTasks => 'Tasks';
  @override
  String get tabWiki => 'Wiki';
  @override
  String get tabSettings => 'Settings';
  @override
  String get loginTitle => 'Sign in to Shinbee Japan';
  @override
  String get loginWithSSO => 'Sign in';
  @override
  String loginError(String error) => 'Sign-in failed: $error';
  @override
  String get loginDomainHint => 'Please sign in with your @your-domain.com account';
  @override
  String get logout => 'Sign out';
  @override
  String get search => 'Search';
  @override
  String get loading => 'Loading...';
  @override
  String get error => 'Error';
  @override
  String get retry => 'Retry';
  @override
  String get noResults => 'No results found';
  @override
  String get parts => 'Parts';
  @override
  String get partCategories => 'Part Categories';
  @override
  String get stock => 'Stock';
  @override
  String get stockLocations => 'Stock Locations';
  @override
  String get purchaseOrders => 'Purchase Orders';
  @override
  String get salesOrders => 'Sales Orders';
  @override
  String get waybill => 'Waybill';
  @override
  String get projects => 'Projects';
  @override
  String get tasks => 'Tasks';
  @override
  String get kanban => 'Kanban';
  @override
  String get calendar => 'Calendar';
  @override
  String get documents => 'Documents';
  @override
  String get collections => 'Collections';
  @override
  String get newDocument => 'New Document';
  @override
  String get editDocument => 'Edit Document';
  @override
  String get save => 'Save';
  @override
  String get cancel => 'Cancel';
  @override
  String get delete => 'Delete';
  @override
  String get confirmDelete => 'Are you sure you want to delete this?';
  @override
  String get settingsTitle => 'Settings';
  @override
  String get settingsLanguage => 'Language';
  @override
  String get settingsTheme => 'Theme';
  @override
  String get themeDark => 'Dark';
  @override
  String get themeLight => 'Light';
  @override
  String get themeSystem => 'System';
  @override
  String get settingsAbout => 'About';
  @override
  String get phoneManagement => 'Phone Management';
  @override
  String get phoneUsers => 'Users';
  @override
  String get phoneDevices => 'Devices';
  @override
  String get phoneExtension => 'Extension';
  @override
  String get phoneName => 'Name';
  @override
  String get phonePassword => 'Password';
  @override
  String get phoneAddUser => 'Add User';
  @override
  String get customizeDashboard => 'Customize Dashboard';
  @override
  String get resetDefaults => 'Reset';
  @override
  String get voiceRequest => 'Voice Request';
  @override
  String get voiceTargetEmail => 'Target email';
  @override
  String get voiceTapToRecord => 'Tap to record';
  @override
  String get voiceRecording => 'Recording...';
  @override
  String get voiceStart => 'Start Recording';
  @override
  String get voiceStop => 'Stop Recording';
  @override
  String get voicePreviewTitle => 'Request Preview';
  @override
  String get voiceTaskTitle => 'Task Title';
  @override
  String get voiceDescription => 'Description';
  @override
  String get voiceDueDate => 'Due Date';
  @override
  String get voiceConfirm => 'Create Task';
  @override
  String get callRequest => 'Call Request';
  @override
  String get callCallerExtension => 'Your extension';
  @override
  String get callTargetExtension => 'Target extension';
  @override
  String get callStart => 'Call';
  @override
  String get callRinging => 'Ringing...';
  @override
  String get callInProgress => 'In Progress';
  @override
  String get callAnalyze => 'Analyze Call';
  @override
  String get callAnalyzing => 'Analyzing...';
  @override
  String get callReady => 'Ready to call';
  @override
  String get callAnalysisResult => 'Call Analysis Result';
  @override
  String get rakutenKeyManagement => 'Rakuten API Key Management';
  @override
  String get rakutenInstructions => 'Renewal Procedure';
  @override
  String get rakutenStep1 => '1. Log in to RMS';
  @override
  String get rakutenStep2 => '2. Open API Key Management page';
  @override
  String get rakutenStep3 => '3. Copy new keys and paste below';
  @override
  String get rakutenSubmitKeys => 'Submit New Keys';
  @override
  String get rakutenSubmit => 'Submit';
  @override
  String get rakutenStatusOk => 'OK';
  @override
  String get rakutenStatusWarning => 'Renewal Recommended';
  @override
  String get rakutenStatusExpired => 'Expired';
  @override
  String get rakutenStatusUnknown => 'Not Set';
  @override
  String get rakutenRenewedAt => 'Last Renewed';
  @override
  String get rakutenAgeDays => 'Age (days)';
  @override
  String get rakutenDaysRemaining => 'Days Remaining';
  @override
  String get pickingList => 'Picking List';
  @override
  String get pickingOrder => 'Picking Order';
  @override
  String get pickingSelectAll => 'Select All';
  @override
  String get pickingScanHint => 'Scan barcode...';
  @override
  String get pickingScanProduct => 'Scan product barcode...';
  @override
  String get pickingNoOrders => 'No outstanding orders';
  @override
  String get pickingNoItems => 'No items';
  @override
  String get pickingNoOrder => 'Order not found';
  @override
  String get pickingGenerateId => 'Generate ID';
  @override
  String get pickingPrintLabel => 'Print Label';
  @override
  String get pickingStartBatch => 'Start Batch Pick';
  @override
  String get pickingBatchMode => 'Batch Picking';
  @override
  String get pickingCustomer => 'Customer';
  @override
  String get pickingItems => 'items';
  @override
  String get pickingComplete => 'Picking complete';
  @override
  String get pickingCompletePick => 'Complete Pick';
  @override
  String get pickingSplitToOrders => 'Split to Orders';
  @override
  String get pickingSplitScanOrder => 'Scan order barcode';
  @override
  String get pickingSplitScanProduct => 'Scan product barcode';
  @override
  String get pickingSplitActive => 'Active order';
  @override
  String get pickingSplitSwitch => 'Switch';
  @override
  String get pickingSplitAssigned => 'Assigned';
  @override
  String get pickingSplitConfirm => 'Confirm Split';
  @override
  String get pickingSplitConfirmed => 'Split confirmed';
  @override
  String get pickingLabelPreview => 'Label Preview';
  @override
  String get pickingPrintHint => 'Press Ctrl+P to open browser print dialog';
  @override
  String get pbxManagement => 'PBX Management';
  @override
  String get pbxExtensions => 'Extensions';
  @override
  String get pbxDayNight => 'Day/Night';
  @override
  String get pbxRoutes => 'Routes';
  @override
  String get pbxStatus => 'Status';
  @override
  String get pbxAddExtension => 'Add Extension';
  @override
  String get pbxDayMode => 'Day Mode';
  @override
  String get pbxNightMode => 'Night Mode';
  @override
  String get pbxOutboundRoutes => 'Outbound Routes';
  @override
  String get pbxInboundRoutes => 'Inbound Routes';
  @override
  String get pbxUptime => 'Uptime';
  @override
  String get pbxChannels => 'Channels';
  @override
  String get pbxEndpointsRegistered => 'Registered Endpoints';
  @override
  String get pbxEndpointsTotal => 'Total Endpoints';
  @override
  String get pbxReload => 'Reload Config';
  @override
  String get pbxReloaded => 'PBX config reloaded';
  @override
  String get staffManagement => 'Staff Management';
  @override
  String get staffDetail => 'Staff Detail';
  @override
  String get staffAdd => 'Add Staff';
  @override
  String get staffEmail => 'Email';
  @override
  String get staffName => 'Display Name';
  @override
  String get staffRole => 'Role';
  @override
  String get staffPermissions => 'Permissions';
  @override
  String get staffPermissionsHint => 'All permissions ON by default. Toggle OFF to restrict.';
  @override
  String get staffGuaranteedByRole => 'Guaranteed by role';
  @override
  String get staffSuperuserAllAccess => 'Superuser has full access to all features.';
  @override
  String get staffDeleteConfirm => 'Delete this staff member?';
}
