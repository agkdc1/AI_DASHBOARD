"""Self-contained HTML admin pages for printer configuration and waybill generation."""

from django.http import HttpResponse, JsonResponse


def printers_admin_page(request):
    """GET /plugin/invoice_print/printers/admin/ → self-contained HTML page."""
    if not request.user or not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Printer Configuration</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
.header { background: #1976d2; color: #fff; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
.header h1 { font-size: 20px; font-weight: 500; }
.btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500; }
.btn-primary { background: #1976d2; color: #fff; }
.btn-primary:hover { background: #1565c0; }
.btn-danger { background: #d32f2f; color: #fff; }
.btn-danger:hover { background: #b71c1c; }
.btn-secondary { background: #757575; color: #fff; }
.btn-secondary:hover { background: #616161; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.container { max-width: 900px; margin: 24px auto; padding: 0 16px; }
.card { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin-bottom: 16px; padding: 16px 20px; }
.card-title { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
.card-meta { font-size: 13px; color: #666; margin-bottom: 8px; }
.card-meta span { margin-right: 12px; }
.card-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 8px; }
.tray-table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
.tray-table th, .tray-table td { text-align: left; padding: 6px 10px; border-bottom: 1px solid #eee; }
.tray-table th { color: #666; font-weight: 500; }
.tray-actions { white-space: nowrap; }
.empty { text-align: center; color: #999; padding: 40px; }

/* Modal overlay */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; align-items: center; justify-content: center; }
.modal-overlay.active { display: flex; }
.modal { background: #fff; border-radius: 8px; width: 480px; max-width: 95vw; max-height: 90vh; overflow-y: auto; padding: 24px; }
.modal h2 { font-size: 18px; margin-bottom: 16px; }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; color: #555; }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
.form-group input:focus, .form-group select:focus { outline: none; border-color: #1976d2; }
.checkbox-group { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
.checkbox-group input[type="checkbox"] { width: auto; }
.tray-editor { border: 1px solid #e0e0e0; border-radius: 4px; padding: 12px; margin-top: 8px; }
.tray-row { display: flex; gap: 8px; margin-bottom: 8px; align-items: center; }
.tray-row input { flex: 1; padding: 6px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
.tray-row .remove-tray { background: none; border: none; color: #d32f2f; cursor: pointer; font-size: 18px; padding: 0 4px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.back-link { color: rgba(255,255,255,0.9); text-decoration: none; font-size: 14px; }
.back-link:hover { color: #fff; }
</style>
</head>
<body>

<div class="header">
    <div style="display:flex;align-items:center;gap:16px;">
        <a href="/" class="back-link">&larr; Back</a>
        <h1>Printer Configuration</h1>
    </div>
    <button class="btn btn-primary" onclick="openAddPrinter()">+ Add Printer</button>
</div>

<div class="container" id="printer-list">
    <div class="empty">Loading...</div>
</div>

<!-- Printer Modal -->
<div class="modal-overlay" id="printer-modal">
    <div class="modal">
        <h2 id="modal-title">Add Printer</h2>
        <input type="hidden" id="edit-printer-id">
        <div class="form-group">
            <label>Name</label>
            <input type="text" id="f-name" placeholder="e.g. Brother QL-820NWB">
        </div>
        <div class="form-group">
            <label>IP Address</label>
            <input type="text" id="f-ip" placeholder="e.g. 192.168.1.100">
        </div>
        <div class="form-group">
            <label>Platform</label>
            <select id="f-platform">
                <option value="yamato">Yamato B2 Cloud</option>
                <option value="sagawa">Sagawa e-Hikari</option>
            </select>
        </div>
        <div class="checkbox-group">
            <input type="checkbox" id="f-multi-tray" onchange="toggleTrayEditor()">
            <label for="f-multi-tray" style="margin-bottom:0;cursor:pointer;">Has multiple trays</label>
        </div>
        <div id="tray-editor-section" style="display:none;">
            <div class="tray-editor">
                <div style="font-size:13px;font-weight:500;color:#555;margin-bottom:8px;">Trays</div>
                <div id="tray-rows"></div>
                <button class="btn btn-secondary btn-sm" onclick="addTrayRow()">+ Add Tray</button>
            </div>
        </div>
        <div class="modal-actions">
            <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
            <button class="btn btn-primary" onclick="savePrinter()">Save</button>
        </div>
    </div>
</div>

<!-- Tray Modal (for editing existing trays) -->
<div class="modal-overlay" id="tray-modal">
    <div class="modal">
        <h2 id="tray-modal-title">Edit Tray</h2>
        <input type="hidden" id="edit-tray-id">
        <input type="hidden" id="edit-tray-printer-id">
        <div class="form-group">
            <label>Name</label>
            <input type="text" id="tf-name" placeholder="e.g. Tray 1">
        </div>
        <div class="form-group">
            <label>Paper Size</label>
            <input type="text" id="tf-paper-size" placeholder="e.g. A4, 100x150mm">
        </div>
        <div class="form-group">
            <label>Label Type</label>
            <input type="text" id="tf-label-type" placeholder="e.g. waybill, invoice">
        </div>
        <div class="modal-actions">
            <button class="btn btn-secondary" onclick="closeTrayModal()">Cancel</button>
            <button class="btn btn-primary" onclick="saveTray()">Save</button>
        </div>
    </div>
</div>

<script>
(function() {
    'use strict';

    var BASE = '/plugin/invoice_print/';

    function getCsrf() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function api(method, path, body) {
        var opts = {
            method: method,
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrf(),
            },
        };
        if (body !== undefined) opts.body = JSON.stringify(body);
        return fetch(BASE + path, opts).then(function(r) {
            if (r.status === 204) return null;
            return r.json().then(function(data) {
                if (!r.ok) throw new Error(data.error || 'Request failed');
                return data;
            });
        });
    }

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    var platformLabels = { yamato: 'Yamato', sagawa: 'Sagawa' };

    // ── Render ──

    window.loadPrinters = function() {
        api('GET', 'printers/').then(function(printers) {
            var container = document.getElementById('printer-list');
            if (!printers.length) {
                container.innerHTML = '<div class="empty">No printers configured. Click "+ Add Printer" to get started.</div>';
                return;
            }
            var html = '';
            printers.forEach(function(p) {
                var trayInfo = p.has_multiple_trays ? (p.trays.length + ' tray' + (p.trays.length !== 1 ? 's' : '')) : 'Single tray';
                html += '<div class="card">';
                html += '<div class="card-title">' + esc(p.name) + '</div>';
                html += '<div class="card-meta">';
                html += '<span>' + esc(p.ip) + '</span>';
                html += '<span>&bull; ' + esc(platformLabels[p.platform] || p.platform) + '</span>';
                html += '<span>&bull; ' + esc(trayInfo) + '</span>';
                html += '</div>';

                if (p.has_multiple_trays) {
                    html += '<table class="tray-table">';
                    html += '<tr><th>Name</th><th>Paper Size</th><th>Label Type</th><th></th></tr>';
                    p.trays.forEach(function(t) {
                        html += '<tr>';
                        html += '<td>' + esc(t.name) + '</td>';
                        html += '<td>' + esc(t.paper_size) + '</td>';
                        html += '<td>' + esc(t.label_type) + '</td>';
                        html += '<td class="tray-actions">';
                        html += '<button class="btn btn-secondary btn-sm" onclick="openEditTray(' + p.id + ',' + JSON.stringify(JSON.stringify(t)) + ')">Edit</button> ';
                        html += '<button class="btn btn-danger btn-sm" onclick="deleteTray(' + p.id + ',' + t.id + ')">×</button>';
                        html += '</td></tr>';
                    });
                    html += '<tr><td colspan="4"><button class="btn btn-secondary btn-sm" onclick="openAddTray(' + p.id + ')">+ Add Tray</button></td></tr>';
                    html += '</table>';
                }

                html += '<div class="card-actions">';
                html += '<button class="btn btn-secondary btn-sm" onclick="openEditPrinter(' + JSON.stringify(JSON.stringify(p)) + ')">Edit</button>';
                html += '<button class="btn btn-danger btn-sm" onclick="deletePrinter(' + p.id + ')">Delete</button>';
                html += '</div>';
                html += '</div>';
            });
            container.innerHTML = html;
        }).catch(function(e) {
            document.getElementById('printer-list').innerHTML = '<div class="empty" style="color:#d32f2f;">Error: ' + esc(e.message) + '</div>';
        });
    };

    // ── Printer modal ──

    window.openAddPrinter = function() {
        document.getElementById('modal-title').textContent = 'Add Printer';
        document.getElementById('edit-printer-id').value = '';
        document.getElementById('f-name').value = '';
        document.getElementById('f-ip').value = '';
        document.getElementById('f-platform').value = 'yamato';
        document.getElementById('f-multi-tray').checked = false;
        document.getElementById('tray-rows').innerHTML = '';
        toggleTrayEditor();
        document.getElementById('printer-modal').classList.add('active');
    };

    window.openEditPrinter = function(jsonStr) {
        var p = JSON.parse(jsonStr);
        document.getElementById('modal-title').textContent = 'Edit Printer';
        document.getElementById('edit-printer-id').value = p.id;
        document.getElementById('f-name').value = p.name;
        document.getElementById('f-ip').value = p.ip;
        document.getElementById('f-platform').value = p.platform;
        document.getElementById('f-multi-tray').checked = p.has_multiple_trays;
        // Populate trays if editing
        var rowsHtml = '';
        (p.trays || []).forEach(function(t) {
            rowsHtml += trayRowHtml(t.name, t.paper_size, t.label_type);
        });
        document.getElementById('tray-rows').innerHTML = rowsHtml;
        toggleTrayEditor();
        document.getElementById('printer-modal').classList.add('active');
    };

    window.closeModal = function() {
        document.getElementById('printer-modal').classList.remove('active');
    };

    window.toggleTrayEditor = function() {
        var show = document.getElementById('f-multi-tray').checked;
        document.getElementById('tray-editor-section').style.display = show ? 'block' : 'none';
    };

    function trayRowHtml(name, paperSize, labelType) {
        return '<div class="tray-row">' +
            '<input type="text" placeholder="Name" value="' + esc(name || '') + '">' +
            '<input type="text" placeholder="Paper Size" value="' + esc(paperSize || '') + '">' +
            '<input type="text" placeholder="Label Type" value="' + esc(labelType || '') + '">' +
            '<button class="remove-tray" onclick="this.parentElement.remove()">&times;</button>' +
            '</div>';
    }

    window.addTrayRow = function() {
        document.getElementById('tray-rows').insertAdjacentHTML('beforeend', trayRowHtml('', '', ''));
    };

    window.savePrinter = function() {
        var id = document.getElementById('edit-printer-id').value;
        var data = {
            name: document.getElementById('f-name').value,
            ip: document.getElementById('f-ip').value,
            platform: document.getElementById('f-platform').value,
            has_multiple_trays: document.getElementById('f-multi-tray').checked,
        };

        // Collect trays from form
        if (data.has_multiple_trays) {
            var rows = document.querySelectorAll('#tray-rows .tray-row');
            data.trays = [];
            rows.forEach(function(row) {
                var inputs = row.querySelectorAll('input');
                if (inputs[0].value.trim()) {
                    data.trays.push({
                        name: inputs[0].value.trim(),
                        paper_size: inputs[1].value.trim(),
                        label_type: inputs[2].value.trim(),
                    });
                }
            });
        }

        if (id) {
            // Edit: update printer, then sync trays
            api('PUT', 'printers/' + id + '/', data).then(function() {
                // For simplicity on edit, delete existing trays and recreate
                return api('GET', 'printers/' + id + '/trays/');
            }).then(function(existingTrays) {
                if (!data.has_multiple_trays) {
                    // Delete all trays if multi-tray is off
                    var deletes = (existingTrays || []).map(function(t) {
                        return api('DELETE', 'printers/' + id + '/trays/' + t.id + '/');
                    });
                    return Promise.all(deletes);
                }
                // Delete old trays, then create new ones
                var deletes = (existingTrays || []).map(function(t) {
                    return api('DELETE', 'printers/' + id + '/trays/' + t.id + '/');
                });
                return Promise.all(deletes).then(function() {
                    var creates = (data.trays || []).map(function(t) {
                        return api('POST', 'printers/' + id + '/trays/', t);
                    });
                    return Promise.all(creates);
                });
            }).then(function() {
                closeModal();
                loadPrinters();
            }).catch(function(e) { alert('Error: ' + e.message); });
        } else {
            // Create new printer (trays included in POST body)
            api('POST', 'printers/', data).then(function() {
                closeModal();
                loadPrinters();
            }).catch(function(e) { alert('Error: ' + e.message); });
        }
    };

    window.deletePrinter = function(id) {
        if (!confirm('Delete this printer and all its trays?')) return;
        api('DELETE', 'printers/' + id + '/').then(function() {
            loadPrinters();
        }).catch(function(e) { alert('Error: ' + e.message); });
    };

    // ── Tray modal (for existing printers) ──

    window.openAddTray = function(printerId) {
        document.getElementById('tray-modal-title').textContent = 'Add Tray';
        document.getElementById('edit-tray-id').value = '';
        document.getElementById('edit-tray-printer-id').value = printerId;
        document.getElementById('tf-name').value = '';
        document.getElementById('tf-paper-size').value = '';
        document.getElementById('tf-label-type').value = '';
        document.getElementById('tray-modal').classList.add('active');
    };

    window.openEditTray = function(printerId, jsonStr) {
        var t = JSON.parse(jsonStr);
        document.getElementById('tray-modal-title').textContent = 'Edit Tray';
        document.getElementById('edit-tray-id').value = t.id;
        document.getElementById('edit-tray-printer-id').value = printerId;
        document.getElementById('tf-name').value = t.name;
        document.getElementById('tf-paper-size').value = t.paper_size;
        document.getElementById('tf-label-type').value = t.label_type;
        document.getElementById('tray-modal').classList.add('active');
    };

    window.closeTrayModal = function() {
        document.getElementById('tray-modal').classList.remove('active');
    };

    window.saveTray = function() {
        var trayId = document.getElementById('edit-tray-id').value;
        var printerId = document.getElementById('edit-tray-printer-id').value;
        var data = {
            name: document.getElementById('tf-name').value,
            paper_size: document.getElementById('tf-paper-size').value,
            label_type: document.getElementById('tf-label-type').value,
        };

        var promise;
        if (trayId) {
            promise = api('PUT', 'printers/' + printerId + '/trays/' + trayId + '/', data);
        } else {
            promise = api('POST', 'printers/' + printerId + '/trays/', data);
        }
        promise.then(function() {
            closeTrayModal();
            loadPrinters();
        }).catch(function(e) { alert('Error: ' + e.message); });
    };

    window.deleteTray = function(printerId, trayId) {
        if (!confirm('Delete this tray?')) return;
        api('DELETE', 'printers/' + printerId + '/trays/' + trayId + '/').then(function() {
            loadPrinters();
        }).catch(function(e) { alert('Error: ' + e.message); });
    };

    // ── Init ──
    loadPrinters();
})();
</script>
</body>
</html>"""

    return HttpResponse(html, content_type="text/html")


def waybill_admin_page(request):
    """GET /plugin/invoice_print/waybill-page/ → self-contained waybill generation page."""
    if not request.user or not request.user.is_authenticated:
        return JsonResponse({"error": "Forbidden"}, status=403)

    html = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>送り状発行</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Hiragino Sans', 'Noto Sans JP', sans-serif; background: #f5f5f5; color: #333; }
.header { background: #1976d2; color: #fff; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
.header h1 { font-size: 20px; font-weight: 500; }
.back-link { color: rgba(255,255,255,0.9); text-decoration: none; font-size: 14px; }
.back-link:hover { color: #fff; }
.container { max-width: 800px; margin: 24px auto; padding: 0 16px; }
.section { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin-bottom: 16px; padding: 20px; }
.section-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #1976d2; border-bottom: 2px solid #e3f2fd; padding-bottom: 8px; }
.form-row { display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-end; }
.form-group { flex: 1; }
.form-group label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; color: #555; }
.form-group input, .form-group select { width: 100%; padding: 8px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
.form-group input:focus, .form-group select:focus { outline: none; border-color: #1976d2; }
.address-display { background: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 4px; padding: 10px; font-size: 14px; min-height: 40px; margin-top: 4px; color: #333; }
.btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500; }
.btn-primary { background: #1976d2; color: #fff; }
.btn-primary:hover { background: #1565c0; }
.btn-secondary { background: #757575; color: #fff; }
.btn-secondary:hover { background: #616161; }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.radio-group { display: flex; gap: 20px; margin-bottom: 12px; }
.radio-group label { cursor: pointer; font-size: 14px; }
.status-box { margin-top: 16px; padding: 12px; border-radius: 4px; font-size: 14px; display: none; }
.status-box.info { display: block; background: #e3f2fd; color: #1565c0; }
.status-box.success { display: block; background: #e8f5e9; color: #2e7d32; }
.status-box.error { display: block; background: #ffebee; color: #c62828; }
.zipcode-row { display: flex; gap: 8px; align-items: flex-end; }
.zipcode-row .form-group { flex: 0 0 160px; }
.manual-toggle { font-size: 13px; color: #1976d2; cursor: pointer; text-decoration: underline; margin-top: 8px; display: inline-block; }
.manual-fields { display: none; margin-top: 12px; }
.manual-fields.active { display: block; }
</style>
</head>
<body>

<div class="header">
    <a href="/" class="back-link">&larr; 戻る</a>
    <h1>送り状発行</h1>
</div>

<div class="container">

<!-- Sender (差出人) -->
<div class="section">
    <div class="section-title">差出人</div>
    <div class="form-row">
        <div class="form-group">
            <label>会社</label>
            <select id="sender-company" onchange="loadAddresses('sender')">
                <option value="">選択してください</option>
            </select>
        </div>
        <div class="form-group">
            <label>住所</label>
            <select id="sender-address" onchange="displayAddress('sender')">
                <option value="">選択してください</option>
            </select>
        </div>
    </div>
    <div class="address-display" id="sender-address-display">住所を選択してください</div>
</div>

<!-- Receiver (届先) -->
<div class="section">
    <div class="section-title">届先</div>
    <div class="form-row">
        <div class="form-group">
            <label>会社</label>
            <select id="receiver-company" onchange="loadAddresses('receiver')">
                <option value="">選択してください</option>
            </select>
        </div>
        <div class="form-group">
            <label>住所</label>
            <select id="receiver-address" onchange="displayAddress('receiver')">
                <option value="">選択してください</option>
            </select>
        </div>
    </div>
    <div class="address-display" id="receiver-address-display">住所を選択してください</div>
    <span class="manual-toggle" onclick="toggleManual()">手動入力に切り替え</span>
    <div class="manual-fields" id="manual-fields">
        <div class="section-title" style="font-size:14px;margin-top:8px;">手動入力</div>
        <div class="form-group" style="margin-bottom:8px;">
            <label>届先名</label>
            <input type="text" id="manual-name" placeholder="会社名または氏名">
        </div>
        <div class="zipcode-row">
            <div class="form-group">
                <label>〒 郵便番号</label>
                <input type="text" id="manual-postal" placeholder="1234567" maxlength="7">
            </div>
            <button class="btn btn-secondary btn-sm" onclick="lookupPostal()" style="margin-bottom:0;">検索</button>
        </div>
        <div id="postal-status" style="font-size:12px;color:#666;margin-top:4px;margin-bottom:8px;"></div>
        <div class="form-row">
            <div class="form-group">
                <label>都道府県</label>
                <input type="text" id="manual-province" placeholder="東京都">
            </div>
            <div class="form-group">
                <label>市区町村</label>
                <input type="text" id="manual-city" placeholder="千代田区">
            </div>
        </div>
        <div class="form-group" style="margin-bottom:8px;">
            <label>町域・番地</label>
            <input type="text" id="manual-line1" placeholder="丸の内1-1-1">
        </div>
        <div class="form-group" style="margin-bottom:8px;">
            <label>建物名・部屋番号</label>
            <input type="text" id="manual-line2" placeholder="">
        </div>
        <div class="form-group" style="margin-bottom:8px;">
            <label>電話番号</label>
            <input type="text" id="manual-phone" placeholder="03-1234-5678">
        </div>
    </div>
</div>

<!-- Carrier & Shipment -->
<div class="section">
    <div class="section-title">配送情報</div>
    <div style="margin-bottom:12px;">
        <label style="font-size:13px;font-weight:500;display:block;margin-bottom:6px;color:#555;">配送業者</label>
        <div class="radio-group">
            <label><input type="radio" name="carrier" value="yamato" checked> ヤマト運輸</label>
            <label><input type="radio" name="carrier" value="sagawa"> 佐川急便</label>
        </div>
    </div>
    <div class="form-group">
        <label>出荷ID</label>
        <input type="text" id="shipment-id" placeholder="出荷IDを入力">
    </div>
    <div style="margin-top:16px;">
        <button class="btn btn-primary" id="submit-btn" onclick="submitWaybill()">送り状を発行</button>
    </div>
    <div class="status-box" id="status-box"></div>
</div>

</div>

<script>
(function() {
    'use strict';

    var BASE = '/plugin/invoice_print/';
    var API_BASE = '/api/';
    var addressCache = {};
    var manualMode = false;

    function getCsrf() {
        var m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }

    function apiFetch(url, opts) {
        opts = opts || {};
        opts.credentials = 'same-origin';
        opts.headers = Object.assign({
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrf(),
        }, opts.headers || {});
        return fetch(url, opts).then(function(r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        });
    }

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    function formatAddress(addr) {
        var postal = addr.postal_code ? ('〒' + addr.postal_code + ' ') : '';
        var parts = [
            addr.province || '',
            addr.postal_city || '',
            addr.line1 || '',
            addr.line2 || '',
        ].filter(function(p) { return p; });
        return postal + parts.join('');
    }

    // Load companies
    function loadCompanies(role, isSupplier) {
        var param = isSupplier ? 'is_supplier=true' : 'is_customer=true';
        apiFetch(API_BASE + 'company/?' + param + '&limit=100').then(function(data) {
            var items = data.results || data;
            var sel = document.getElementById(role + '-company');
            sel.innerHTML = '<option value="">選択してください</option>';
            items.forEach(function(c) {
                sel.innerHTML += '<option value="' + c.pk + '">' + esc(c.name) + '</option>';
            });
        }).catch(function(e) {
            console.error('Failed to load companies:', e);
        });
    }

    // Load addresses for a company
    window.loadAddresses = function(role) {
        var companyId = document.getElementById(role + '-company').value;
        var sel = document.getElementById(role + '-address');
        sel.innerHTML = '<option value="">選択してください</option>';
        document.getElementById(role + '-address-display').textContent = '住所を選択してください';

        if (!companyId) return;

        apiFetch(API_BASE + 'company/address/?company=' + companyId + '&limit=100').then(function(data) {
            var items = data.results || data;
            addressCache[role] = {};
            items.forEach(function(a) {
                addressCache[role][a.pk] = a;
                var label = a.title || formatAddress(a);
                sel.innerHTML += '<option value="' + a.pk + '">' + esc(label) + '</option>';
            });
        }).catch(function(e) {
            console.error('Failed to load addresses:', e);
        });
    };

    // Display formatted address
    window.displayAddress = function(role) {
        var addrId = document.getElementById(role + '-address').value;
        var display = document.getElementById(role + '-address-display');

        if (!addrId || !addressCache[role] || !addressCache[role][addrId]) {
            display.textContent = '住所を選択してください';
            return;
        }

        var addr = addressCache[role][addrId];
        display.textContent = formatAddress(addr);
    };

    // Manual entry toggle
    window.toggleManual = function() {
        manualMode = !manualMode;
        var el = document.getElementById('manual-fields');
        el.classList.toggle('active', manualMode);
    };

    // Postal code lookup
    window.lookupPostal = function() {
        var postal = document.getElementById('manual-postal').value.replace(/[^0-9]/g, '');
        var statusEl = document.getElementById('postal-status');

        if (postal.length !== 7) {
            statusEl.textContent = '7桁の郵便番号を入力してください';
            statusEl.style.color = '#d32f2f';
            return;
        }

        statusEl.textContent = '検索中...';
        statusEl.style.color = '#666';

        fetch('https://zipcloud.ibsnet.co.jp/api/search?zipcode=' + postal)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.status === 200 && data.results && data.results.length > 0) {
                    var result = data.results[0];
                    document.getElementById('manual-province').value = result.address1 || '';
                    document.getElementById('manual-city').value = result.address2 || '';
                    document.getElementById('manual-line1').value = result.address3 || '';
                    statusEl.textContent = '住所を自動入力しました';
                    statusEl.style.color = '#388e3c';
                } else {
                    statusEl.textContent = '該当する住所が見つかりません';
                    statusEl.style.color = '#d32f2f';
                }
            })
            .catch(function() {
                statusEl.textContent = '検索に失敗しました';
                statusEl.style.color = '#d32f2f';
            });
    };

    // Submit waybill
    window.submitWaybill = function() {
        var carrier = document.querySelector('input[name="carrier"]:checked').value;
        var shipmentId = document.getElementById('shipment-id').value.trim();
        var statusBox = document.getElementById('status-box');
        var submitBtn = document.getElementById('submit-btn');

        if (!shipmentId) {
            statusBox.className = 'status-box error';
            statusBox.textContent = '出荷IDを入力してください';
            return;
        }

        submitBtn.disabled = true;
        statusBox.className = 'status-box info';
        statusBox.textContent = '送信中...';

        var body = {
            carrier: carrier,
            shipment_id: parseInt(shipmentId, 10) || shipmentId,
        };

        // If manual mode, include manual address info
        if (manualMode) {
            body.recipient_name = document.getElementById('manual-name').value;
            body.recipient_postal = document.getElementById('manual-postal').value;
            body.recipient_province = document.getElementById('manual-province').value;
            body.recipient_city = document.getElementById('manual-city').value;
            body.recipient_line1 = document.getElementById('manual-line1').value;
            body.recipient_line2 = document.getElementById('manual-line2').value;
            body.recipient_phone = document.getElementById('manual-phone').value;
        }

        apiFetch(BASE + 'generate/', {
            method: 'POST',
            body: JSON.stringify(body),
        }).then(function(result) {
            statusBox.className = 'status-box info';
            statusBox.textContent = 'ジョブ送信完了: ' + result.job_id + ' (処理中...)';
            pollStatus(result.job_id);
        }).catch(function(e) {
            statusBox.className = 'status-box error';
            statusBox.textContent = 'エラー: ' + e.message;
            submitBtn.disabled = false;
        });
    };

    function pollStatus(jobId) {
        var attempts = 0;
        var maxAttempts = 120;

        function check() {
            if (attempts++ >= maxAttempts) {
                var sb = document.getElementById('status-box');
                sb.className = 'status-box error';
                sb.textContent = 'タイムアウトしました。ステータスを確認してください。';
                document.getElementById('submit-btn').disabled = false;
                return;
            }

            apiFetch(BASE + 'status/' + encodeURIComponent(jobId) + '/').then(function(job) {
                var sb = document.getElementById('status-box');

                if (job.status === 'completed') {
                    var tracking = (job.result && job.result.tracking_number) || '';
                    var msg = '完了';
                    if (tracking) msg += ' - 追跡番号: ' + tracking;
                    sb.className = 'status-box success';
                    sb.innerHTML = esc(msg) +
                        ' <a href="' + BASE + 'pdf/' + encodeURIComponent(jobId) +
                        '/" style="color:#1976d2;font-weight:500;">PDF ダウンロード</a>';
                    document.getElementById('submit-btn').disabled = false;
                } else if (job.status === 'failed') {
                    sb.className = 'status-box error';
                    sb.textContent = '失敗: ' + (job.error || '不明なエラー');
                    document.getElementById('submit-btn').disabled = false;
                } else {
                    sb.className = 'status-box info';
                    sb.textContent = '処理中... (' + job.status + ')';
                    setTimeout(check, 3000);
                }
            }).catch(function() {
                setTimeout(check, 5000);
            });
        }

        setTimeout(check, 2000);
    }

    // Init: load companies
    loadCompanies('sender', true);
    loadCompanies('receiver', false);

    // Pre-select default sender if configured
    // (The plugin setting is server-side; we try to select the first supplier)
})();
</script>
</body>
</html>"""

    return HttpResponse(html, content_type="text/html")
