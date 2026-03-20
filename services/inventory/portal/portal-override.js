/*
 * Portal Override JS
 * Enforces Google-SSO-only login on portal.your-domain.com.
 * Injected by nginx sub_filter before </head>.
 *
 * Targets InvenTree 1.x React/Mantine SPA.
 * AuthenticationForm renders:
 *   <Group> SsoButton(s) </Group>   <-- keep visible
 *   <Divider />                     <-- hide
 *   <form> classic login </form>    <-- hide
 *
 * - Sets default language to Japanese (ja) for new visitors
 * - Seeds waybill dashboard widget as the default
 * - MutationObserver hides non-SSO elements and non-dashboard nav items
 * - Detects staff users and injects a "Printer Setup" link
 * - Syncs user profile language and widgets to server on login
 * - One-time reload if observeProfile() clobbers seeded widgets
 * - Auto-disconnects after 30 seconds
 */
(function portalOverride() {
    'use strict';

    var MAX_WAIT_MS = 30000;
    var WAYBILL_WIDGET = 'p-invoice-print-invoice-print-waybill';
    var ADDRESS_WIDGET = 'p-invoice-print-address-book';
    var DEFAULT_WIDGETS = [WAYBILL_WIDGET, ADDRESS_WIDGET];
    var DEFAULT_LAYOUTS = {
        lg: [
            { w: 4, h: 4, x: 0, y: 0, i: WAYBILL_WIDGET, minW: 2, minH: 1 },
            { w: 8, h: 4, x: 4, y: 0, i: ADDRESS_WIDGET, minW: 3, minH: 2 }
        ]
    };

    // --- Seed localStorage before Zustand hydrates ---
    // InvenTree stores language in 'session-settings' (Zustand persist).
    // Set Japanese + waybill widget for new visitors or default 'en'.
    function ensureWidgets(state) {
        // Ensure all DEFAULT_WIDGETS are present; add missing ones
        if (!state.widgets) state.widgets = [];
        var changed = false;
        for (var i = 0; i < DEFAULT_WIDGETS.length; i++) {
            if (state.widgets.indexOf(DEFAULT_WIDGETS[i]) === -1) {
                state.widgets.push(DEFAULT_WIDGETS[i]);
                changed = true;
            }
        }
        if (changed) {
            state.showSampleDashboard = false;
            state.layouts = DEFAULT_LAYOUTS;
        }
        return changed;
    }

    function seedSessionSettings() {
        try {
            var stored = localStorage.getItem('session-settings');
            if (stored) {
                var parsed = JSON.parse(stored);
                if (parsed.state) {
                    var changed = false;

                    if (!parsed.state.language || parsed.state.language === 'en') {
                        parsed.state.language = 'ja';
                        changed = true;
                    }

                    if (ensureWidgets(parsed.state)) changed = true;

                    if (changed) {
                        localStorage.setItem('session-settings', JSON.stringify(parsed));
                    }
                }
            } else {
                localStorage.setItem('session-settings', JSON.stringify({
                    state: {
                        language: 'ja',
                        widgets: DEFAULT_WIDGETS,
                        showSampleDashboard: false,
                        layouts: DEFAULT_LAYOUTS
                    },
                    version: 0
                }));
            }
        } catch (e) {}
    }

    seedSessionSettings();

    function getCsrf() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function hideClassicLogin() {
        var userInput = document.querySelector('[aria-label="login-username"]');
        if (userInput) {
            var form = userInput.closest('form');
            if (form) form.style.display = 'none';
        }

        var dividers = document.querySelectorAll('[class*="Divider-root"]');
        dividers.forEach(function (el) { el.style.display = 'none'; });

        var regInput = document.querySelector('[aria-label="register-username"]');
        if (regInput) {
            var regForm = regInput.closest('form');
            if (regForm) regForm.style.display = 'none';
        }

        var regDividers = document.querySelectorAll('[class*="Divider-label"]');
        regDividers.forEach(function (el) {
            var text = el.textContent || '';
            if (text.indexOf('SSO') !== -1 || text.indexOf('other') !== -1) {
                var divider = el.closest('[class*="Divider-root"]');
                if (divider) divider.style.display = 'none';
            }
        });
    }

    var HIDDEN_NAV_LABELS = [
        'Parts', '部品',
        'Stock', '在庫',
        'Build', '製造',
        'Manufacturing', '製造',
        'Purchasing', '購買',
        'Sales', '販売',
        'Users', 'ユーザー',
        'Groups', 'グループ',
        'Scan Barcode', 'バーコードスキャン',
    ];

    function hideNavDrawerItems() {
        var drawer = document.querySelector('[class*="Drawer-body"]');
        if (!drawer) return;

        var buttons = drawer.querySelectorAll('button');
        buttons.forEach(function (btn) {
            var text = (btn.textContent || '').trim();
            for (var i = 0; i < HIDDEN_NAV_LABELS.length; i++) {
                if (text === HIDDEN_NAV_LABELS[i]) {
                    btn.style.display = 'none';
                    break;
                }
            }
        });
    }

    // --- Post-login: fix empty widgets caused by observeProfile() ---
    // observeProfile() in auth.tsx syncs server-side profile → Zustand
    // in-memory state. If the profile has no widgets, it clobbers our
    // localStorage seed. Detect this on the dashboard and do a one-time
    // reload after re-seeding localStorage.
    function fixWidgetsAfterLogin() {
        // Only act on the dashboard page (not login)
        var path = window.location.pathname;
        if (path.indexOf('/web/home') === -1 && path !== '/web/' && path !== '/') return;

        // Already applied this session? Don't loop.
        if (sessionStorage.getItem('portal-widget-fix')) return;

        try {
            var s = localStorage.getItem('session-settings');
            if (!s) return;
            var p = JSON.parse(s);
            if (p.state && ensureWidgets(p.state)) {
                localStorage.setItem('session-settings', JSON.stringify(p));
                sessionStorage.setItem('portal-widget-fix', '1');
                window.location.reload();
            }
        } catch (e) {}
    }

    function injectWaybillTab() {
        if (document.getElementById('portal-waybill-tab')) return;

        // Find the InvenTree header tab list
        var tabList = document.querySelector('[role="tablist"]');
        if (!tabList) return;

        var tab = document.createElement('a');
        tab.id = 'portal-waybill-tab';
        tab.href = '/plugin/invoice_print/waybill-page/';
        tab.textContent = '送り状発行';
        tab.style.cssText = [
            'display: inline-flex',
            'align-items: center',
            'padding: 8px 16px',
            'font-size: 14px',
            'font-weight: 500',
            'color: #1976d2',
            'text-decoration: none',
            'border-bottom: 2px solid transparent',
            'cursor: pointer',
            'white-space: nowrap',
        ].join('; ');
        tab.addEventListener('mouseenter', function () {
            tab.style.borderBottomColor = '#1976d2';
        });
        tab.addEventListener('mouseleave', function () {
            tab.style.borderBottomColor = 'transparent';
        });
        // Force full page navigation — React Router intercepts clicks
        // inside the Tabs component and does client-side routing
        tab.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            window.location.href = '/plugin/invoice_print/waybill-page/';
        });
        tabList.appendChild(tab);
    }

    function injectAdminLink() {
        if (document.getElementById('portal-admin-link')) return;

        fetch('/api/user/me/', {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        })
        .then(function (resp) {
            if (!resp.ok) return null;
            return resp.json();
        })
        .then(function (data) {
            if (!data) return;

            // Sync language and widgets to server-side profile so that
            // observeProfile() will read the right values on future logins.
            var needsPatch = {};
            if (data.profile && (!data.profile.language || data.profile.language === 'en')) {
                needsPatch.language = 'ja';
            }

            var profileWidgets = data.profile && data.profile.widgets;
            var pw = profileWidgets && profileWidgets.widgets ? profileWidgets.widgets : [];
            var missingWidget = false;
            for (var i = 0; i < DEFAULT_WIDGETS.length; i++) {
                if (pw.indexOf(DEFAULT_WIDGETS[i]) === -1) { missingWidget = true; break; }
            }
            if (!profileWidgets || !profileWidgets.widgets || missingWidget) {
                var merged = pw.slice();
                for (var j = 0; j < DEFAULT_WIDGETS.length; j++) {
                    if (merged.indexOf(DEFAULT_WIDGETS[j]) === -1) merged.push(DEFAULT_WIDGETS[j]);
                }
                needsPatch.widgets = {
                    widgets: merged,
                    layouts: DEFAULT_LAYOUTS
                };
            }

            if (Object.keys(needsPatch).length > 0) {
                fetch('/api/user/profile/', {
                    method: 'PATCH',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCsrf(),
                    },
                    body: JSON.stringify(needsPatch),
                }).catch(function () {});
            }

            if (data.is_staff || data.is_superuser) {
                var link = document.createElement('a');
                link.id = 'portal-admin-link';
                link.href = '/plugin/invoice_print/printers/admin/';
                link.textContent = 'Printer Setup';
                link.style.cssText = [
                    'position: fixed',
                    'bottom: 20px',
                    'right: 20px',
                    'background: #1976d2',
                    'color: #fff',
                    'padding: 10px 18px',
                    'border-radius: 6px',
                    'text-decoration: none',
                    'font-size: 14px',
                    'font-weight: 500',
                    'box-shadow: 0 2px 8px rgba(0,0,0,0.2)',
                    'z-index: 9999',
                    'cursor: pointer',
                ].join('; ');
                link.addEventListener('mouseenter', function () {
                    link.style.background = '#1565c0';
                });
                link.addEventListener('mouseleave', function () {
                    link.style.background = '#1976d2';
                });
                document.body.appendChild(link);
            }
        })
        .catch(function () {
            // Not logged in or API unavailable
        });
    }

    function init() {
        hideClassicLogin();
        injectAdminLink();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // MutationObserver to enforce hiding as React renders
    var observer = new MutationObserver(function () {
        hideClassicLogin();
        hideNavDrawerItems();
        injectWaybillTab();
        fixWidgetsAfterLogin();
    });

    observer.observe(document.body || document.documentElement, {
        childList: true,
        subtree: true,
    });

    // Auto-disconnect after MAX_WAIT_MS
    setTimeout(function () {
        observer.disconnect();
    }, MAX_WAIT_MS);
})();
