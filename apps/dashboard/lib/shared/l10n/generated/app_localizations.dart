import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_ja.dart';
import 'app_localizations_ko.dart';

/// Callers can lookup localized strings with an instance of S
/// returned by `S.of(context)`.
abstract class S {
  S(String locale) : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static S of(BuildContext context) {
    return Localizations.of<S>(context, S)!;
  }

  static const LocalizationsDelegate<S> delegate = _SDelegate();

  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
    delegate,
    GlobalMaterialLocalizations.delegate,
    GlobalCupertinoLocalizations.delegate,
    GlobalWidgetsLocalizations.delegate,
  ];

  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('ja'),
    Locale('ko'),
  ];

  String get appTitle;
  String get tabHome;
  String get tabInventory;
  String get tabTasks;
  String get tabWiki;
  String get tabSettings;
  String get loginTitle;
  String get loginWithSSO;
  String loginError(String error);
  String get loginDomainHint;
  String get logout;
  String get search;
  String get loading;
  String get error;
  String get retry;
  String get noResults;
  String get parts;
  String get partCategories;
  String get stock;
  String get stockLocations;
  String get purchaseOrders;
  String get salesOrders;
  String get waybill;
  String get projects;
  String get tasks;
  String get kanban;
  String get calendar;
  String get documents;
  String get collections;
  String get newDocument;
  String get editDocument;
  String get save;
  String get cancel;
  String get delete;
  String get confirmDelete;
  String get settingsTitle;
  String get settingsLanguage;
  String get settingsTheme;
  String get themeDark;
  String get themeLight;
  String get themeSystem;
  String get settingsAbout;
  String get phoneManagement;
  String get phoneUsers;
  String get phoneDevices;
  String get phoneExtension;
  String get phoneName;
  String get phonePassword;
  String get phoneAddUser;
  String get customizeDashboard;
  String get resetDefaults;
  String get voiceRequest;
  String get voiceTargetEmail;
  String get voiceTapToRecord;
  String get voiceRecording;
  String get voiceStart;
  String get voiceStop;
  String get voicePreviewTitle;
  String get voiceTaskTitle;
  String get voiceDescription;
  String get voiceDueDate;
  String get voiceConfirm;
  String get callRequest;
  String get callCallerExtension;
  String get callTargetExtension;
  String get callStart;
  String get callRinging;
  String get callInProgress;
  String get callAnalyze;
  String get callAnalyzing;
  String get callReady;
  String get callAnalysisResult;
  String get rakutenKeyManagement;
  String get rakutenInstructions;
  String get rakutenStep1;
  String get rakutenStep2;
  String get rakutenStep3;
  String get rakutenSubmitKeys;
  String get rakutenSubmit;
  String get rakutenStatusOk;
  String get rakutenStatusWarning;
  String get rakutenStatusExpired;
  String get rakutenStatusUnknown;
  String get rakutenRenewedAt;
  String get rakutenAgeDays;
  String get rakutenDaysRemaining;
  String get pickingList;
  String get pickingOrder;
  String get pickingSelectAll;
  String get pickingScanHint;
  String get pickingScanProduct;
  String get pickingNoOrders;
  String get pickingNoItems;
  String get pickingNoOrder;
  String get pickingGenerateId;
  String get pickingPrintLabel;
  String get pickingStartBatch;
  String get pickingBatchMode;
  String get pickingCustomer;
  String get pickingItems;
  String get pickingComplete;
  String get pickingCompletePick;
  String get pickingSplitToOrders;
  String get pickingSplitScanOrder;
  String get pickingSplitScanProduct;
  String get pickingSplitActive;
  String get pickingSplitSwitch;
  String get pickingSplitAssigned;
  String get pickingSplitConfirm;
  String get pickingSplitConfirmed;
  String get pickingLabelPreview;
  String get pickingPrintHint;
  String get pbxManagement;
  String get pbxExtensions;
  String get pbxDayNight;
  String get pbxRoutes;
  String get pbxStatus;
  String get pbxAddExtension;
  String get pbxDayMode;
  String get pbxNightMode;
  String get pbxOutboundRoutes;
  String get pbxInboundRoutes;
  String get pbxUptime;
  String get pbxChannels;
  String get pbxEndpointsRegistered;
  String get pbxEndpointsTotal;
  String get pbxReload;
  String get pbxReloaded;
  String get staffManagement;
  String get staffDetail;
  String get staffAdd;
  String get staffEmail;
  String get staffName;
  String get staffRole;
  String get staffPermissions;
  String get staffPermissionsHint;
  String get staffGuaranteedByRole;
  String get staffSuperuserAllAccess;
  String get staffDeleteConfirm;
}

class _SDelegate extends LocalizationsDelegate<S> {
  const _SDelegate();

  @override
  Future<S> load(Locale locale) {
    return SynchronousFuture<S>(lookupS(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'ja', 'ko'].contains(locale.languageCode);

  @override
  bool shouldReload(_SDelegate old) => false;
}

S lookupS(Locale locale) {
  switch (locale.languageCode) {
    case 'ja':
      return SJa();
    case 'ko':
      return SKo();
    case 'en':
    default:
      return SEn();
  }
}
