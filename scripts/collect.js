/**
 * collect.js —— 在抖音商品详情页的浏览器上下文里运行，收集三类图片。
 *
 * 前置：由 build_payload.py 注入 window.__DY_PACK_URLS__（候选签名接口地址数组）。
 * 不在本文件里做字符串替换——URL 含 & ，用 sed 注入会被当成"整个匹配"展开。
 *
 * 手动用法：
 *   agent-browser network requests --filter "pack/detail" \
 *     | python3 scripts/build_payload.py > /tmp/prelude.js
 *   cat /tmp/prelude.js scripts/collect.js | agent-browser eval --stdin > raw.json
 *
 * 输出：JSON 字符串（主图 / 详情图 / 买家秀）
 */
(function () {
  var CANDIDATES = (window.__DY_PACK_URLS__ || []).filter(function (u) {
    return typeof u === 'string' && u.indexOf('http') === 0;
  });

  /* ---------- 1. 从 URL 里解析 product_id / promotion_id ---------- */

  function decodeTimes(s, n) {
    for (var i = 0; i < n; i++) {
      try { s = decodeURIComponent(s); } catch (e) { break; }
    }
    return s;
  }

  var href = location.href;
  var dec = decodeTimes(href, 3); // detail_schema 是双重编码的

  function pick(re) {
    var m = dec.match(re);
    return m ? m[1] : null;
  }

  var qs;
  try { qs = new URL(href).searchParams; } catch (e) { qs = new URLSearchParams(); }

  var promotionId = qs.get('promotion_id') || pick(/promotion_id[^0-9]{1,6}(\d{15,22})/);

  // 兜底：alkey=1128_<author>_<item>_<promotion>_011
  if (!promotionId) {
    var seg = (qs.get('alkey') || '').split('_');
    if (seg.length >= 4 && /^\d{15,22}$/.test(seg[3])) promotionId = seg[3];
  }

  var productId = qs.get('id') || pick(/[?&]id[^0-9]{1,6}(\d{15,22})/);

  /* ---------- 2. DOM 侧：主图 + 买家秀 ---------- */

  function bgUrls(scopeSel, mustContain) {
    var root = document.querySelector(scopeSel);
    if (!root) return [];
    var out = [];
    var nodes = root.querySelectorAll('*');
    for (var i = 0; i < nodes.length; i++) {
      var bg = getComputedStyle(nodes[i]).backgroundImage;
      if (!bg || bg.indexOf('url(') === -1) continue;
      if (mustContain && bg.indexOf(mustContain) === -1) continue;
      var m = bg.match(/url\("?([^")]+)"?\)/);
      if (m) out.push(m[1]);
    }
    // 部分 A/B 版本用 <img> 实现，一并收
    var imgs = root.querySelectorAll('img');
    for (var j = 0; j < imgs.length; j++) {
      var src = imgs[j].currentSrc || imgs[j].src;
      if (src && src.indexOf('http') === 0) out.push(src);
    }
    return out;
  }

  // 主图：只保留 shop-material 素材，过滤 logo / 图标 / data URI。
  // 注意保留 `ecom-shop-material/` 前缀，和接口返回的 uri 保持同构，方便统一下载。
  var main = [];
  var mainRaw = bgUrls('.head-figure', 'ecom-shop-material');
  for (var k = 0; k < mainRaw.length; k++) {
    var mm = mainRaw[k].match(/(ecom-shop-material\/[^~?]+)/);
    if (mm && main.indexOf(mm[1]) === -1) main.push(mm[1]);
  }

  var buyershow = [];
  var bsRaw = bgUrls('[class*=buyershow]', 'commentpic');
  for (var b = 0; b < bsRaw.length; b++) {
    if (buyershow.indexOf(bsRaw[b]) === -1) buyershow.push(bsRaw[b]);
  }

  /* ---------- 3. 接口侧：详情长图（必须 POST + promotion_id） ---------- */

  function build(detail, extra) {
    var payload = {
      ok: detail.length > 0,
      product_id: productId,
      promotion_id: promotionId,
      main: main,
      detail: detail,
      buyershow: buyershow
    };
    Object.keys(extra || {}).forEach(function (k) { payload[k] = extra[k]; });
    return JSON.stringify(payload);
  }

  function bail(reason, extra) {
    var e = extra || {};
    e.reason = reason;
    return build([], e);
  }

  if (!CANDIDATES.length) {
    return bail('missing_pack_url: 未拿到签名接口地址，先执行 network requests --filter pack/detail');
  }
  if (!promotionId) {
    return bail('missing_promotion_id: URL 里没解析出 promotion_id');
  }

  // 依次尝试每条候选 URL —— 有的签名不带 msToken，回放只会返回空 body
  var tried = [];

  function tryNext(i) {
    if (i >= CANDIDATES.length) {
      return bail('all_candidates_failed', {
        tried: tried,
        hint: '所有候选签名回放都拿到空 body。最常见原因：候选 URL 缺 msToken，' +
              '或 a_bogus 是短签名（约 44 字符）——这类签名只能被页面自己消费一次，无法回放。' +
              '解决：重新加载页面再抓签名（run.sh 已内置重试），或先访问 douyin.com 让 msToken 生效。'
      });
    }
    return fetch(CANDIDATES[i], {
      method: 'POST',                       // GET 会返回空 body
      credentials: 'include',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: 'promotion_id=' + promotionId   // 用 product_id 会 14001006 参数不合法
    })
      .then(function (r) { return r.text(); })
      .then(function (text) {
        var j;
        try { j = JSON.parse(text); } catch (e) { j = null; }
        if (!j || j.status_code !== 0) {
          tried.push({ i: i, code: j ? j.status_code : 'not_json',
                       msg: j ? j.status_msg : text.slice(0, 60) });
          return tryNext(i + 1);
        }
        var info = j.detail_info || {};
        // detail_imgs_new 是同样内容的嵌套结构，优先用扁平的 detail_imgs
        var list = info.detail_imgs || [];
        var detail = [];
        for (var n = 0; n < list.length; n++) {
          var uri = list[n] && list[n].uri;
          if (uri && detail.indexOf(uri) === -1) detail.push(uri);
        }

        // SKU / 规格：分享落地页的 DOM 里完全没有，只能从完整响应的
        // product_format / detail_config 里拿。这里不做 schema 假设——
        // 原样透传，交给下游自己解析（未验证过具体结构）。
        function dump(o) {
          if (o == null) return null;
          try {
            var s = JSON.stringify(o);
            return s.length > 20000 ? s.slice(0, 20000) + '…' : s;
          } catch (e) { return null; }
        }

        return build(detail, {
          candidate_index: i,
          tried: tried,
          has_product_format: !!info.product_format,
          has_detail_config: !!info.detail_config,
          product_format: dump(info.product_format),
          detail_config: dump(info.detail_config),
          detail_info_keys: Object.keys(info)
        });
      })
      .catch(function (e) {
        tried.push({ i: i, code: 'exception', msg: String(e).slice(0, 60) });
        return tryNext(i + 1);
      });
  }

  return tryNext(0);
})();
