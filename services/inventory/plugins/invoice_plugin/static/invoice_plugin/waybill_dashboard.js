/**
 * InvenTree Dashboard Widget: 送り状発行 (Waybill Generation)
 *
 * Renders a compact waybill generation form in the InvenTree dashboard.
 * Supports carrier selection, shipment ID input, job submission, and
 * status polling with PDF download link.
 */

export function renderDashboardItem(target, data) {
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
            return r.json().then(function(d) {
                if (!r.ok) throw new Error(d.error || 'Request failed');
                return d;
            });
        });
    }

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s || '';
        return d.innerHTML;
    }

    // Build the widget HTML
    var html = '' +
        '<div style="padding:12px;">' +
        '  <div style="margin-bottom:10px;">' +
        '    <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px;">' +
        '      配送業者' +
        '    </label>' +
        '    <label style="margin-right:16px;cursor:pointer;">' +
        '      <input type="radio" name="wb-carrier" value="yamato" checked> ヤマト運輸' +
        '    </label>' +
        '    <label style="cursor:pointer;">' +
        '      <input type="radio" name="wb-carrier" value="sagawa"> 佐川急便' +
        '    </label>' +
        '  </div>' +
        '  <div style="margin-bottom:10px;">' +
        '    <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px;">' +
        '      出荷ID' +
        '    </label>' +
        '    <input type="text" id="wb-shipment-id" placeholder="出荷IDを入力" ' +
        '      style="width:100%;padding:6px 8px;border:1px solid #ccc;border-radius:4px;font-size:14px;">' +
        '  </div>' +
        '  <div style="display:flex;gap:8px;align-items:center;">' +
        '    <button id="wb-submit" style="padding:8px 16px;background:#1976d2;color:#fff;border:none;' +
        '      border-radius:4px;cursor:pointer;font-size:14px;font-weight:500;">発行</button>' +
        '    <a href="' + BASE + 'waybill-page/" style="font-size:13px;color:#1976d2;">詳細入力</a>' +
        '  </div>' +
        '  <div id="wb-status" style="margin-top:10px;font-size:13px;"></div>' +
        '</div>';

    target.innerHTML = html;

    // Event handlers
    var submitBtn = target.querySelector('#wb-submit');
    var statusDiv = target.querySelector('#wb-status');

    submitBtn.addEventListener('click', function() {
        var carrier = target.querySelector('input[name="wb-carrier"]:checked').value;
        var shipmentId = target.querySelector('#wb-shipment-id').value.trim();

        if (!shipmentId) {
            statusDiv.innerHTML = '<span style="color:#d32f2f;">出荷IDを入力してください</span>';
            return;
        }

        submitBtn.disabled = true;
        statusDiv.innerHTML = '<span style="color:#666;">送信中...</span>';

        api('POST', 'generate/', {
            carrier: carrier,
            shipment_id: parseInt(shipmentId, 10) || shipmentId,
        }).then(function(result) {
            statusDiv.innerHTML = '<span style="color:#388e3c;">ジョブ送信完了: ' + esc(result.job_id) + '</span>';
            pollStatus(result.job_id);
        }).catch(function(e) {
            statusDiv.innerHTML = '<span style="color:#d32f2f;">エラー: ' + esc(e.message) + '</span>';
            submitBtn.disabled = false;
        });
    });

    function pollStatus(jobId) {
        var attempts = 0;
        var maxAttempts = 60;

        function check() {
            if (attempts++ >= maxAttempts) {
                statusDiv.innerHTML = '<span style="color:#f57c00;">タイムアウト - ステータスを確認してください</span>';
                submitBtn.disabled = false;
                return;
            }

            api('GET', 'status/' + encodeURIComponent(jobId) + '/').then(function(job) {
                if (job.status === 'completed') {
                    var tracking = (job.result && job.result.tracking_number) || '';
                    var inner = '<span style="color:#388e3c;">完了</span>';
                    if (tracking) {
                        inner += ' - 追跡番号: <strong>' + esc(tracking) + '</strong>';
                    }
                    inner += ' <a href="' + BASE + 'pdf/' + encodeURIComponent(jobId) +
                             '/" style="color:#1976d2;">PDF ダウンロード</a>';
                    statusDiv.innerHTML = inner;
                    submitBtn.disabled = false;
                } else if (job.status === 'failed') {
                    statusDiv.innerHTML = '<span style="color:#d32f2f;">失敗: ' +
                        esc(job.error || '不明なエラー') + '</span>';
                    submitBtn.disabled = false;
                } else {
                    statusDiv.innerHTML = '<span style="color:#666;">処理中... (' + esc(job.status) + ')</span>';
                    setTimeout(check, 3000);
                }
            }).catch(function() {
                setTimeout(check, 5000);
            });
        }

        setTimeout(check, 2000);
    }
}
