import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'auth/auth_state.dart';
import 'auth/login_screen.dart';
import 'auth/token_manager.dart';
import 'settings_screen.dart';
import '../shared/widgets/bottom_nav_shell.dart';
import '../shared/widgets/error_page.dart';
import '../home/screens/home_screen.dart';
import '../home/screens/customize_screen.dart';
import '../inventree/screens/dashboard_screen.dart';
import '../inventree/screens/part_list_screen.dart';
import '../inventree/screens/part_detail_screen.dart';
import '../inventree/screens/stock_list_screen.dart';
import '../inventree/screens/stock_detail_screen.dart';
import '../inventree/screens/po_list_screen.dart';
import '../inventree/screens/so_list_screen.dart';
import '../inventree/screens/waybill_screen.dart';
import '../vikunja/screens/projects_screen.dart';
import '../vikunja/screens/project_detail_screen.dart';
import '../vikunja/screens/task_detail_screen.dart';
import '../vikunja/screens/kanban_screen.dart';
import '../vikunja/screens/calendar_screen.dart';
import '../outline/screens/documents_screen.dart';
import '../outline/screens/document_detail_screen.dart';
import '../outline/screens/editor_screen.dart';
import '../outline/screens/collection_screen.dart';
import '../outline/screens/search_screen.dart';
import '../phone/screens/phone_admin_screen.dart';
import '../rakuten/screens/rakuten_key_screen.dart';
import '../voice_request/screens/voice_request_screen.dart';
import '../call_request/screens/call_request_screen.dart';
import '../picking/screens/picking_list_screen.dart';
import '../picking/screens/picking_order_screen.dart';
import '../picking/screens/batch_picking_screen.dart';
import '../picking/screens/split_screen.dart';
import '../picking/screens/label_preview_screen.dart';
import '../pbx/screens/pbx_screen.dart';
import '../staff/screens/staff_list_screen.dart';
import '../staff/screens/staff_detail_screen.dart';
import '../seating/screens/seat_picker_screen.dart';
import '../seating/screens/seat_assignment_screen.dart';
import '../seating/admin/office_list_screen.dart';
import '../seating/admin/floor_editor_screen.dart';
import '../fax_review/screens/fax_review_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

final routerProvider = Provider.autoDispose<GoRouter>((ref) {
  final authState = ref.watch(tokenManagerProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: '/home',
    redirect: (context, state) {
      final isAuth = authState is Authenticated;
      final isLoggingIn = state.matchedLocation == '/login';

      if (!isAuth && !isLoggingIn) return '/login';
      if (isAuth && isLoggingIn) return '/home';
      return null;
    },
    errorBuilder: (context, state) => ErrorPage(error: state.error),
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            BottomNavShell(navigationShell: navigationShell),
        branches: [
          // Tab 0: Home
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/home',
              builder: (context, state) => const HomeScreen(),
              routes: [
                GoRoute(
                  path: 'customize',
                  builder: (context, state) => const CustomizeScreen(),
                ),
                GoRoute(
                  path: 'voice-request',
                  builder: (context, state) =>
                      const VoiceRequestScreen(),
                ),
                GoRoute(
                  path: 'call-request',
                  builder: (context, state) =>
                      const CallRequestScreen(),
                ),
                GoRoute(
                  path: 'staff',
                  builder: (context, state) =>
                      const StaffListScreen(),
                  routes: [
                    GoRoute(
                      path: ':email',
                      builder: (context, state) => StaffDetailScreen(
                        email: Uri.decodeComponent(
                            state.pathParameters['email']!),
                      ),
                    ),
                  ],
                ),
                GoRoute(
                  path: 'picking',
                  builder: (context, state) =>
                      const PickingListScreen(),
                  routes: [
                    GoRoute(
                      path: 'order/:id',
                      builder: (context, state) => PickingOrderScreen(
                        orderId: state.pathParameters['id']!,
                      ),
                    ),
                    GoRoute(
                      path: 'batch',
                      builder: (context, state) =>
                          const BatchPickingScreen(),
                    ),
                    GoRoute(
                      path: 'split',
                      builder: (context, state) =>
                          const SplitScreen(),
                    ),
                    GoRoute(
                      path: 'label/:id',
                      builder: (context, state) => LabelPreviewScreen(
                        orderId: state.pathParameters['id']!,
                      ),
                    ),
                  ],
                ),
                GoRoute(
                  path: 'fax-review',
                  builder: (context, state) =>
                      const FaxReviewScreen(),
                ),
                GoRoute(
                  path: 'seating',
                  builder: (context, state) =>
                      const SeatPickerScreen(),
                  routes: [
                    GoRoute(
                      path: 'my-seat',
                      builder: (context, state) =>
                          const SeatAssignmentScreen(),
                    ),
                    GoRoute(
                      path: 'admin',
                      builder: (context, state) =>
                          const OfficeListScreen(),
                    ),
                    GoRoute(
                      path: 'admin/floor/:floorId',
                      builder: (context, state) => FloorEditorScreen(
                        floorId: int.parse(
                            state.pathParameters['floorId']!),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ]),
          // Tab 1: Inventory
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/inventory',
              builder: (context, state) =>
                  const InventoryDashboardScreen(),
              routes: [
                GoRoute(
                  path: 'parts',
                  builder: (context, state) => const PartListScreen(),
                ),
                GoRoute(
                  path: 'parts/:id',
                  builder: (context, state) => PartDetailScreen(
                    partId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: 'stock',
                  builder: (context, state) => const StockListScreen(),
                ),
                GoRoute(
                  path: 'stock/:id',
                  builder: (context, state) => StockDetailScreen(
                    stockId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: 'orders/purchase',
                  builder: (context, state) => const POListScreen(),
                ),
                GoRoute(
                  path: 'orders/sales',
                  builder: (context, state) => const SOListScreen(),
                ),
                GoRoute(
                  path: 'waybill',
                  builder: (context, state) => const WaybillScreen(),
                ),
              ],
            ),
          ]),
          // Tab 2: Tasks (Vikunja)
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/tasks',
              builder: (context, state) => const ProjectsScreen(),
              routes: [
                GoRoute(
                  path: ':id',
                  builder: (context, state) => ProjectDetailScreen(
                    projectId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: ':id/kanban',
                  builder: (context, state) => KanbanScreen(
                    projectId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: ':id/calendar',
                  builder: (context, state) => CalendarScreen(
                    projectId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: 'task/:id',
                  builder: (context, state) => TaskDetailScreen(
                    taskId: state.pathParameters['id']!,
                  ),
                ),
              ],
            ),
          ]),
          // Tab 3: Wiki (Outline)
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/wiki',
              builder: (context, state) => const DocumentsScreen(),
              routes: [
                GoRoute(
                  path: 'doc/:id',
                  builder: (context, state) => DocumentDetailScreen(
                    documentId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: 'doc/:id/edit',
                  builder: (context, state) => EditorScreen(
                    documentId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: 'collection/:id',
                  builder: (context, state) => CollectionScreen(
                    collectionId: state.pathParameters['id']!,
                  ),
                ),
                GoRoute(
                  path: 'search',
                  builder: (context, state) => const SearchScreen(),
                ),
              ],
            ),
          ]),
          // Tab 4: Settings
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/settings',
              builder: (context, state) => const SettingsScreen(),
              routes: [
                GoRoute(
                  path: 'phone',
                  builder: (context, state) => const PhoneAdminScreen(),
                ),
                GoRoute(
                  path: 'rakuten',
                  builder: (context, state) => const RakutenKeyScreen(),
                ),
                GoRoute(
                  path: 'pbx',
                  builder: (context, state) => const PbxScreen(),
                ),
              ],
            ),
          ]),
        ],
      ),
    ],
  );
});
