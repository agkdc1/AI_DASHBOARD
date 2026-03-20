/**
 * InvenTree Dashboard Widget: 住所録 (Address Book)
 *
 * Manages company addresses via InvenTree REST API.
 * Addresses are used as sender/receiver on waybills.
 */

export function renderDashboardItem(target, data) {
    'use strict';

    var API = '/api/';

    function getCsrf() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function apiFetch(method, path, body) {
        var opts = {
            method: method,
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRFToken': getCsrf(),
            },
        };
        if (body !== undefined) opts.body = JSON.stringify(body);
        return fetch(API + path, opts).then(function(r) {
            if (method === 'DELETE' && r.status === 204) return null;
            return r.json().then(function(d) {
                if (!r.ok) throw new Error(d.detail || d.error || JSON.stringify(d));
                return d;
            });
        });
    }

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    // State
    var companies = [];
    var selectedCompanyId = null;
    var addresses = [];
    var editingId = null; // address pk being edited, or 'new'

    // --- Render ---

    function render() {
        var h = '<div style="padding:12px;font-size:13px;">';

        // Company selector row
        h += '<div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;">';
        h += '<select id="ab-company" style="flex:1;padding:5px 8px;border:1px solid #ccc;border-radius:4px;font-size:13px;">';
        h += '<option value="">-- 会社を選択 --</option>';
        for (var i = 0; i < companies.length; i++) {
            var c = companies[i];
            var sel = c.pk === selectedCompanyId ? ' selected' : '';
            h += '<option value="' + c.pk + '"' + sel + '>' + esc(c.name) + '</option>';
        }
        h += '</select>';
        h += '<button id="ab-new-company" style="padding:5px 10px;background:#1976d2;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;white-space:nowrap;">新規会社</button>';
        h += '</div>';

        if (selectedCompanyId) {
            // Address list
            if (addresses.length === 0 && editingId === null) {
                h += '<div style="color:#888;margin-bottom:8px;">住所が登録されていません</div>';
            }

            for (var j = 0; j < addresses.length; j++) {
                var a = addresses[j];
                if (editingId === a.pk) {
                    h += renderForm(a);
                } else {
                    h += renderAddressRow(a);
                }
            }

            if (editingId === 'new') {
                h += renderForm(null);
            }

            if (editingId === null) {
                h += '<button id="ab-add" style="padding:5px 12px;background:#388e3c;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;margin-top:4px;">住所追加</button>';
            }
        }

        h += '<div id="ab-msg" style="margin-top:8px;font-size:12px;"></div>';
        h += '</div>';

        target.innerHTML = h;
        bindEvents();
    }

    function renderAddressRow(a) {
        var parts = [];
        if (a.postal_code) parts.push('〒' + esc(a.postal_code));
        if (a.province) parts.push(esc(a.province));
        if (a.postal_city) parts.push(esc(a.postal_city));
        if (a.line1) parts.push(esc(a.line1));
        if (a.line2) parts.push(esc(a.line2));
        var addrStr = parts.join(' ');

        var h = '<div style="border:1px solid #e0e0e0;border-radius:4px;padding:8px;margin-bottom:6px;">';
        h += '<div style="display:flex;justify-content:space-between;align-items:flex-start;">';
        h += '<div style="flex:1;min-width:0;">';
        h += '<div style="font-weight:600;font-size:13px;">' + esc(a.title || '(無題)');
        if (a.primary) h += ' <span style="color:#1976d2;font-size:11px;">★ 主要</span>';
        h += '</div>';
        h += '<div style="color:#555;font-size:12px;margin-top:2px;word-break:break-all;">' + addrStr + '</div>';
        if (a.phone) h += '<div style="color:#555;font-size:12px;">TEL: ' + esc(a.phone) + '</div>';
        h += '</div>';
        h += '<div style="display:flex;gap:4px;margin-left:8px;flex-shrink:0;">';
        h += '<button class="ab-edit" data-pk="' + a.pk + '" style="padding:3px 8px;background:#f5f5f5;border:1px solid #ccc;border-radius:3px;cursor:pointer;font-size:11px;">編集</button>';
        h += '<button class="ab-del" data-pk="' + a.pk + '" style="padding:3px 8px;background:#ffebee;border:1px solid #ef9a9a;border-radius:3px;cursor:pointer;font-size:11px;color:#c62828;">削除</button>';
        h += '</div>';
        h += '</div></div>';
        return h;
    }

    function renderForm(existing) {
        var a = existing || {};
        var h = '<div style="border:1px solid #1976d2;border-radius:4px;padding:10px;margin-bottom:6px;background:#fafafa;">';
        h += '<div style="font-weight:600;margin-bottom:8px;font-size:13px;">' + (existing ? '住所編集' : '新規住所') + '</div>';

        var fields = [
            { id: 'title', label: 'タイトル', ph: '例: 本社, 倉庫', val: a.title },
            { id: 'postal_code', label: '〒 郵便番号', ph: '123-4567', val: a.postal_code },
            { id: 'province', label: '都道府県', ph: '東京都', val: a.province },
            { id: 'postal_city', label: '市区町村', ph: '千代田区', val: a.postal_city },
            { id: 'line1', label: '町域・番地', ph: '丸の内1-1-1', val: a.line1 },
            { id: 'line2', label: '建物名', ph: 'ビル名 3F', val: a.line2 },
        ];

        for (var i = 0; i < fields.length; i++) {
            var f = fields[i];
            h += '<div style="margin-bottom:5px;">';
            h += '<label style="font-size:11px;color:#666;display:block;">' + f.label + '</label>';
            h += '<input id="ab-f-' + f.id + '" type="text" value="' + esc(f.val || '') + '" placeholder="' + f.ph + '" ';
            h += 'style="width:100%;padding:4px 6px;border:1px solid #ccc;border-radius:3px;font-size:13px;box-sizing:border-box;">';
            h += '</div>';
        }

        h += '<label style="font-size:12px;cursor:pointer;display:block;margin-bottom:8px;">';
        h += '<input type="checkbox" id="ab-f-primary"' + (a.primary ? ' checked' : '') + '> 主要住所に設定';
        h += '</label>';

        h += '<div style="display:flex;gap:6px;">';
        h += '<button id="ab-save" style="padding:5px 12px;background:#1976d2;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px;">保存</button>';
        h += '<button id="ab-cancel" style="padding:5px 12px;background:#f5f5f5;border:1px solid #ccc;border-radius:4px;cursor:pointer;font-size:12px;">キャンセル</button>';
        h += '</div></div>';
        return h;
    }

    // --- Events ---

    function bindEvents() {
        var sel = target.querySelector('#ab-company');
        if (sel) sel.addEventListener('change', function() {
            selectedCompanyId = this.value ? parseInt(this.value, 10) : null;
            editingId = null;
            if (selectedCompanyId) loadAddresses();
            else { addresses = []; render(); }
        });

        var newCoBtn = target.querySelector('#ab-new-company');
        if (newCoBtn) newCoBtn.addEventListener('click', createCompany);

        var addBtn = target.querySelector('#ab-add');
        if (addBtn) addBtn.addEventListener('click', function() {
            editingId = 'new';
            render();
        });

        var editBtns = target.querySelectorAll('.ab-edit');
        editBtns.forEach(function(btn) {
            btn.addEventListener('click', function() {
                editingId = parseInt(this.getAttribute('data-pk'), 10);
                render();
            });
        });

        var delBtns = target.querySelectorAll('.ab-del');
        delBtns.forEach(function(btn) {
            btn.addEventListener('click', function() {
                var pk = parseInt(this.getAttribute('data-pk'), 10);
                deleteAddress(pk);
            });
        });

        var saveBtn = target.querySelector('#ab-save');
        if (saveBtn) saveBtn.addEventListener('click', saveAddress);

        var cancelBtn = target.querySelector('#ab-cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', function() {
            editingId = null;
            render();
        });
    }

    function showMsg(text, color) {
        var el = target.querySelector('#ab-msg');
        if (el) {
            el.innerHTML = '<span style="color:' + color + ';">' + esc(text) + '</span>';
            setTimeout(function() { if (el) el.innerHTML = ''; }, 3000);
        }
    }

    // --- API calls ---

    function loadCompanies() {
        apiFetch('GET', 'company/?limit=200&ordering=name').then(function(data) {
            companies = data.results || data;
            render();
            if (selectedCompanyId) loadAddresses();
        }).catch(function(e) {
            showMsg('会社一覧の取得に失敗: ' + e.message, '#d32f2f');
        });
    }

    function loadAddresses() {
        apiFetch('GET', 'company/address/?company=' + selectedCompanyId + '&limit=100').then(function(data) {
            addresses = data.results || data;
            render();
        }).catch(function(e) {
            showMsg('住所の取得に失敗: ' + e.message, '#d32f2f');
        });
    }

    function createCompany() {
        var name = prompt('会社名を入力してください:');
        if (!name || !name.trim()) return;

        apiFetch('POST', 'company/', {
            name: name.trim(),
            is_customer: true,
            is_supplier: false,
        }).then(function(co) {
            companies.push(co);
            selectedCompanyId = co.pk;
            addresses = [];
            editingId = null;
            render();
            showMsg('会社「' + co.name + '」を作成しました', '#388e3c');
        }).catch(function(e) {
            showMsg('会社の作成に失敗: ' + e.message, '#d32f2f');
        });
    }

    function saveAddress() {
        var formData = {
            company: selectedCompanyId,
            title: (target.querySelector('#ab-f-title') || {}).value || '',
            postal_code: (target.querySelector('#ab-f-postal_code') || {}).value || '',
            province: (target.querySelector('#ab-f-province') || {}).value || '',
            postal_city: (target.querySelector('#ab-f-postal_city') || {}).value || '',
            line1: (target.querySelector('#ab-f-line1') || {}).value || '',
            line2: (target.querySelector('#ab-f-line2') || {}).value || '',
            primary: (target.querySelector('#ab-f-primary') || {}).checked || false,
        };

        if (!formData.title.trim()) {
            showMsg('タイトルを入力してください', '#d32f2f');
            return;
        }

        var saveBtn = target.querySelector('#ab-save');
        if (saveBtn) saveBtn.disabled = true;

        if (editingId === 'new') {
            apiFetch('POST', 'company/address/', formData).then(function() {
                editingId = null;
                showMsg('住所を追加しました', '#388e3c');
                loadAddresses();
            }).catch(function(e) {
                showMsg('保存に失敗: ' + e.message, '#d32f2f');
                if (saveBtn) saveBtn.disabled = false;
            });
        } else {
            apiFetch('PATCH', 'company/address/' + editingId + '/', formData).then(function() {
                editingId = null;
                showMsg('住所を更新しました', '#388e3c');
                loadAddresses();
            }).catch(function(e) {
                showMsg('更新に失敗: ' + e.message, '#d32f2f');
                if (saveBtn) saveBtn.disabled = false;
            });
        }
    }

    function deleteAddress(pk) {
        if (!confirm('この住所を削除しますか？')) return;

        apiFetch('DELETE', 'company/address/' + pk + '/').then(function() {
            showMsg('住所を削除しました', '#388e3c');
            loadAddresses();
        }).catch(function(e) {
            showMsg('削除に失敗: ' + e.message, '#d32f2f');
        });
    }

    // --- Init ---
    loadCompanies();
}
