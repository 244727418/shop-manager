# -*- coding: utf-8 -*-
"""Minimal Chrome/Edge monitor for the Pinduoduo merchant web console."""

import base64
import json
import os
import socket
import struct
import subprocess
import time
from urllib.parse import quote, urlparse

import requests


PDD_MERCHANT_URL = "https://mms.pinduoduo.com/"
PDD_PRICE_MANAGEMENT_URL = "https://mms.pinduoduo.com/goods/goods-price-management"


class BrowserMonitorError(Exception):
    pass


class DevToolsWebSocket:
    def __init__(self, websocket_url, timeout=3):
        parsed = urlparse(websocket_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        if parsed.query:
            self.path += "?" + parsed.query
        self.timeout = timeout
        self.sock = None
        self.message_id = 0

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self._recv_until(b"\r\n\r\n")
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise BrowserMonitorError("Chrome DevTools WebSocket handshake failed")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _recv_until(self, marker):
        data = b""
        while marker not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def _send_text(self, text):
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))

        mask = os.urandom(4)
        masked = bytes(payload[i] ^ mask[i % 4] for i in range(length))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_text(self):
        first = self.sock.recv(2)
        if len(first) < 2:
            raise BrowserMonitorError("Chrome DevTools WebSocket closed")
        opcode = first[0] & 0x0F
        masked = bool(first[1] & 0x80)
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self.sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self.sock.recv(8))[0]
        mask = self.sock.recv(4) if masked else b""
        payload = b""
        while len(payload) < length:
            chunk = self.sock.recv(length - len(payload))
            if not chunk:
                raise BrowserMonitorError("Chrome DevTools WebSocket closed")
            payload += chunk
        if masked:
            payload = bytes(payload[i] ^ mask[i % 4] for i in range(length))
        if opcode == 8:
            raise BrowserMonitorError("Chrome DevTools WebSocket closed")
        if opcode not in (1, 2):
            return None
        return payload.decode("utf-8", errors="replace")

    def call(self, method, params=None):
        self.message_id += 1
        message_id = self.message_id
        self._send_text(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            text = self._recv_text()
            if not text:
                continue
            data = json.loads(text)
            if data.get("id") == message_id:
                if "error" in data:
                    raise BrowserMonitorError(str(data["error"]))
                return data.get("result", {})
        raise BrowserMonitorError("Chrome DevTools WebSocket response timed out")


class PddBrowserMonitor:
    _ports_by_profile_root = {}
    _processes_by_profile_root = {}

    def __init__(self, base_dir, port=9223):
        self.base_dir = base_dir
        self.legacy_port = port
        self.store_base_port = port + 100
        self.port = port
        self.process = None
        self.legacy_profile_root = os.path.join(base_dir, "browser_profiles", "pdd_merchant")
        self.profile_root = os.path.join(base_dir, "browser_profiles", "pdd_merchant_profiles")
        self.active_profile_key = "default"
        self.profile_ports = self._ports_by_profile_root.setdefault(self.profile_root, {})
        self.profile_processes = self._processes_by_profile_root.setdefault(self.profile_root, {})
        self.profile_dir = self._profile_dir_for_key(self.active_profile_key)

    def _profile_key_for_store(self, store_id):
        value = str(store_id or "").strip()
        if not value:
            return "default"
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
        return f"store_{safe}"

    def _profile_dir_for_key(self, key):
        if key == "default":
            return self.legacy_profile_root
        return os.path.join(self.profile_root, key)

    def _port_for_key(self, key):
        if key == "default":
            return self.legacy_port
        if key in self.profile_ports:
            return self.profile_ports[key]
        store_id_text = key.replace("store_", "", 1)
        if store_id_text.isdigit():
            port = self.store_base_port + int(store_id_text)
            self.profile_ports[key] = port
            return port
        used_ports = set(self.profile_ports.values())
        for port in range(self.store_base_port + 1000, self.store_base_port + 1100):
            if port in used_ports:
                continue
            self.profile_ports[key] = port
            return port
        raise BrowserMonitorError("没有可用的拼多多浏览器调试端口")

    def set_store_context(self, store_id):
        key = self._profile_key_for_store(store_id)
        self.active_profile_key = key
        self.port = self._port_for_key(key)
        self.process = self.profile_processes.get(key)
        self.profile_dir = self._profile_dir_for_key(key)
        return key

    def start(self):
        if self.is_devtools_alive():
            return
        browser_path = self._find_browser()
        if not browser_path:
            raise BrowserMonitorError("未找到 Chrome 或 Edge 浏览器")

        os.makedirs(self.profile_dir, exist_ok=True)
        args = [
            browser_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.profile_dir}",
            "--new-window",
            PDD_MERCHANT_URL,
        ]
        self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.profile_processes[self.active_profile_key] = self.process

    def activate_store_browser(self, store_id=None, open_url=True, open_new_tab=False):
        if store_id is not None:
            self.set_store_context(store_id)
        was_running = self.is_devtools_alive()
        if not was_running:
            self.start()
            return {"running": False, "started": True, "profile_dir": self.profile_dir, "port": self.port}
        if not open_url:
            return {"running": True, "started": False, "profile_dir": self.profile_dir, "port": self.port}
        if not open_new_tab:
            return {"running": True, "started": False, "profile_dir": self.profile_dir, "port": self.port}
        try:
            requests.put(
                f"http://127.0.0.1:{self.port}/json/new?{PDD_MERCHANT_URL}",
                timeout=2,
            )
        except Exception:
            pass
        return {"running": True, "started": False, "profile_dir": self.profile_dir, "port": self.port}

    def open_merchant_page(self, store_id=None, open_new_tab=False):
        return self.activate_store_browser(store_id, open_url=True, open_new_tab=open_new_tab)

    def open_price_management_page(self, store_id=None):
        state = self.activate_store_browser(store_id, open_url=True, open_new_tab=False)
        if state.get("started"):
            time.sleep(1.0)

        target = self._get_pdd_target()
        if not target:
            return {"ok": False, "status": "未找到拼多多商家端页签，请确认浏览器已打开"}

        script = r"""
(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  await sleep(800);

  const spans = Array.from(document.querySelectorAll('span.nav-item-text'));
  const targetSpan = spans.find(node => clean(node.innerText || node.textContent) === '价格管理')
    || spans.find(node => clean(node.innerText || node.textContent).includes('价格管理'));
  if (!targetSpan) {
    return { ok: false, status: '未找到 span.nav-item-text 价格管理入口' };
  }

  const clickable = targetSpan.closest('a, button, [role="button"], li, div') || targetSpan;
  clickable.scrollIntoView({ block: 'center', inline: 'center' });
  await sleep(150);
  clickable.click();
  await sleep(1200);
  return { ok: true, status: '已点击价格管理入口' };
})()
"""
        try:
            with DevToolsWebSocket(target.get("webSocketDebuggerUrl"), timeout=8) as ws:
                result = ws.call("Runtime.evaluate", {"expression": script, "returnByValue": True, "awaitPromise": True})
                value = result.get("result", {}).get("value", {})
                return value if isinstance(value, dict) else {"ok": False, "status": "点击价格管理脚本未返回有效结果"}
        except Exception as exc:
            return {"ok": False, "status": f"打开价格管理页面失败：{exc}"}

    def search_price_management_product(self, product_id):
        product_id = str(product_id or "").strip()
        if not product_id:
            return {"ok": False, "status": "商品ID为空，未执行搜索"}
        if not self.is_devtools_alive():
            return {"ok": False, "status": "浏览器未运行，未执行搜索"}
        target = self._get_pdd_target(prefer_price=True)
        if not target:
            return {"ok": False, "status": "未找到拼多多商家端页签，未执行搜索"}

        product_id_json = json.dumps(product_id, ensure_ascii=False)
        script = f"""
(async () => {{
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const productId = {product_id_json};
  const clean = value => String(value || '').replace(/\\s+/g, ' ').trim();
  await sleep(1200);

  const setValue = (input, value) => {{
    const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};

  const exactInputs = Array.from(document.querySelectorAll('input[class*="IPT_input_"], textarea[class*="IPT_input_"]'));
  const candidates = Array.from(document.querySelectorAll('input, textarea')).filter(input => {{
    const text = clean([
      input.placeholder,
      input.getAttribute('aria-label'),
      input.getAttribute('data-testid'),
      input.name,
      input.id,
      input.className
    ].join(' '));
    const type = String(input.type || '').toLowerCase();
    if (type && ['button', 'checkbox', 'radio', 'submit'].includes(type)) return false;
    return /商品|ID|编号|goods|search|搜索|标题/.test(text);
  }});
  const allInputs = Array.from(document.querySelectorAll('input, textarea')).filter(input => {{
    const type = String(input.type || '').toLowerCase();
    return !type || !['button', 'checkbox', 'radio', 'submit'].includes(type);
  }});
  const input = exactInputs[0] || candidates[0] || allInputs[0];
  if (!input) return {{ ok: false, status: '未找到价格管理搜索输入框' }};

  input.focus();
  setValue(input, productId);
  input.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
  input.dispatchEvent(new KeyboardEvent('keyup', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
  await sleep(250);

  const exactButtons = Array.from(document.querySelectorAll('button[class*="BTN_outerWrapper_"][class*="BTN_primary_"][class*="BTN_medium_"]'));
  const buttons = Array.from(document.querySelectorAll('button,[role="button"],a')).filter(node => {{
    const text = clean(node.innerText || node.textContent || node.getAttribute('aria-label'));
    return /查询|搜索|筛选/.test(text);
  }});
  const button = exactButtons.find(node => /查询/.test(clean(node.innerText || node.textContent || node.getAttribute('aria-label'))))
    || exactButtons[0]
    || buttons[0];
  if (button) button.click();
  await sleep(500);
  return {{ ok: true, status: `已尝试搜索商品ID：${{productId}}` }};
}})()
"""
        try:
            with DevToolsWebSocket(target.get("webSocketDebuggerUrl"), timeout=8) as ws:
                result = ws.call("Runtime.evaluate", {"expression": script, "returnByValue": True, "awaitPromise": True})
                value = result.get("result", {}).get("value", {})
                return value if isinstance(value, dict) else {"ok": False, "status": "搜索脚本未返回有效结果"}
        except Exception as exc:
            return {"ok": False, "status": f"搜索商品ID失败：{exc}"}

    def is_devtools_alive(self):
        try:
            requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=0.8)
            return True
        except Exception:
            return False

    def inspect(self):
        if not self.is_devtools_alive():
            return {
                "running": False,
                "logged_in": False,
                "status": "浏览器未运行",
                "links": [],
                "url": "",
                "title": "",
            }

        target = self._get_pdd_target()
        if not target:
            return {
                "running": True,
                "logged_in": False,
                "status": "浏览器已打开，未找到拼多多商家端页签",
                "links": [],
                "url": "",
                "title": "",
            }

        url = target.get("url", "")
        title = target.get("title", "")
        page_data = self._evaluate_page(target.get("webSocketDebuggerUrl"))
        body_text = page_data.get("body_text", "")
        links = page_data.get("price_links", [])
        product_total_count = page_data.get("product_total_count")
        product_visible_count = page_data.get("product_visible_count")
        product_count_source = page_data.get("product_count_source", "")
        is_goods_list = bool(page_data.get("is_goods_list"))
        on_sale_count = page_data.get("on_sale_count")
        on_sale_source = page_data.get("on_sale_source", "")
        product_ids = page_data.get("product_ids", [])
        block_product_ids = page_data.get("block_product_ids", [])
        product_blocks = page_data.get("product_blocks", [])
        page_link_ids = page_data.get("page_link_ids", [])
        current_code_detail = page_data.get("current_code_detail", {})

        login_markers = ("登录", "验证码", "扫码", "账号")
        merchant_markers = ("价格管理", "商品管理", "店铺", "营销", "订单")
        logged_in = (
            "login" not in url.lower()
            and any(marker in body_text for marker in merchant_markers)
            and not all(marker in body_text for marker in login_markers)
        )

        if is_goods_list and on_sale_count is not None:
            status = f"商品列表: 在售中 {on_sale_count} 个商品"
        elif is_goods_list:
            status = "商品列表已打开，未读取到在售中数量"
        elif links:
            status = f"已识别到价格管理相关入口 {len(links)} 个"
        elif logged_in:
            status = "已登录商家端，暂未识别到价格管理入口"
        else:
            status = "等待用户登录拼多多商家端"

        return {
            "running": True,
            "logged_in": logged_in,
            "status": status,
            "links": links,
            "product_total_count": product_total_count,
            "product_visible_count": product_visible_count,
            "product_count_source": product_count_source,
            "on_sale_count": on_sale_count,
            "on_sale_source": on_sale_source,
            "product_ids": product_ids,
            "block_product_ids": block_product_ids,
            "product_blocks": product_blocks,
            "page_link_ids": page_link_ids,
            "current_code_detail": current_code_detail,
            "is_goods_list": is_goods_list,
            "url": url,
            "title": title,
        }

    def inspect_price_management(self):
        if not self.is_devtools_alive():
            return {
                "running": False,
                "is_price_management": False,
                "status": "浏览器未运行",
                "items": [],
                "url": "",
                "title": "",
            }

        target = self._get_pdd_target(prefer_price=True)
        if not target:
            return {
                "running": True,
                "is_price_management": False,
                "status": "浏览器已打开，未找到拼多多商家端页签",
                "items": [],
                "url": "",
                "title": "",
            }

        url = target.get("url", "")
        title = target.get("title", "")
        page_data = self._evaluate_price_management_page(target.get("webSocketDebuggerUrl"))
        is_price_management = bool(page_data.get("is_price_management"))
        items = page_data.get("items") or []
        status = (
            f"价格管理页已抓取 {len(items)} 个商品"
            if is_price_management
            else "当前页面不是价格管理界面"
        )
        return {
            "running": True,
            "is_price_management": is_price_management,
            "status": status,
            "items": items,
            "visible_rows": page_data.get("visible_rows"),
            "debug": page_data.get("debug", {}),
            "body_text": page_data.get("body_text", ""),
            "url": url,
            "title": title,
        }

    def _get_pdd_target(self, prefer_price=False):
        try:
            targets = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=1.5).json()
        except Exception:
            return None

        pages = [t for t in targets if t.get("type") == "page"]
        if prefer_price:
            for target in pages:
                url = target.get("url", "")
                title = target.get("title", "")
                if "goods-price-management" in url or "价格管理" in title:
                    return target
        for target in pages:
            url = target.get("url", "")
            if "pinduoduo.com" in url or "yangkeduo.com" in url:
                return target
        return pages[0] if pages else None

    def _evaluate_page(self, websocket_url):
        if not websocket_url:
            return {"body_text": "", "price_links": []}

        script = r"""
;(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const bodyText = (document.body && document.body.innerText || '').slice(0, 50000);
  const nodes = Array.from(document.querySelectorAll('a,button,[role="button"],[data-testid],div,span'));
  const priceLinks = [];
  for (const node of nodes) {
    const text = (node.innerText || node.textContent || '').trim().replace(/\s+/g, ' ');
    const href = node.href || node.getAttribute('href') || '';
    if (!text && !href) continue;
    if (text.includes('价格管理') || href.includes('price')) {
      priceLinks.push({ text: text.slice(0, 120), href });
    }
    if (priceLinks.length >= 20) break;
  }

  const normalizedText = bodyText.replace(/\s+/g, ' ');
  const isGoodsList = /商品列表|商品管理|商品ID|商品名称|商品标题|在售中|已售罄|仓库中/.test(normalizedText);
  const parseNumber = value => {
    const n = Number(String(value || '').replace(/,/g, ''));
    return Number.isFinite(n) ? n : null;
  };

  function extractOnSaleCount() {
    const directPatterns = [
      /在售中\s*[（(]\s*([0-9,]+)\s*[）)]/,
      /在售中\s+([0-9,]+)\s*(?:个|件|条|款)?/,
      /在售商品\s*[：:]?\s*([0-9,]+)\s*(?:个|件|条|款)?/
    ];
    for (const pattern of directPatterns) {
      const match = normalizedText.match(pattern);
      if (match) {
        return { count: parseNumber(match[1]), source: match[0] };
      }
    }

    const candidateNodes = Array.from(document.querySelectorAll(
      '[role="tab"],button,a,li,span,div,[class*="tab"],[class*="Tab"],[class*="status"],[class*="Status"]'
    ));
    for (const node of candidateNodes) {
      const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
      if (!text || !text.includes('在售中')) continue;

      const localPatterns = [
        /在售中\s*[（(]?\s*([0-9,]+)\s*[）)]?/,
        /在售中.*?([0-9,]+)/
      ];
      for (const pattern of localPatterns) {
        const match = text.match(pattern);
        if (match) {
          return { count: parseNumber(match[1]), source: text.slice(0, 120) };
        }
      }

      const parentText = node.parentElement ? (node.parentElement.innerText || '').replace(/\s+/g, ' ').trim() : '';
      const parentMatch = parentText.match(/在售中[^0-9]{0,20}([0-9,]+)/);
      if (parentMatch) {
        return { count: parseNumber(parentMatch[1]), source: parentText.slice(0, 160) };
      }

      let sibling = node.nextElementSibling;
      for (let i = 0; sibling && i < 3; i += 1, sibling = sibling.nextElementSibling) {
        const siblingText = (sibling.innerText || sibling.textContent || '').replace(/\s+/g, ' ').trim();
        const siblingMatch = siblingText.match(/^([0-9,]+)$/);
        if (siblingMatch) {
          return { count: parseNumber(siblingMatch[1]), source: `${text} ${siblingText}` };
        }
      }
    }
    return { count: null, source: '' };
  }

  const onSale = extractOnSaleCount();
  function extractProductIds() {
    const ids = new Set();
    const addId = value => {
      const text = String(value || '');
      const matches = [
        ...text.matchAll(/(?:商品ID|商品id|商品编号|goods_id|goodsId|goodsIdList|goodsId=|goods_id=)[^\d]{0,20}(\d{6,})/g),
        ...text.matchAll(/[?&](?:goods_id|goodsId|goodsIdList)=(\d{6,})/g)
      ];
      for (const match of matches) ids.add(match[1]);
    };

    addId(normalizedText);
    const attrNodes = Array.from(document.querySelectorAll('a,button,[role="button"],tr,div,span'));
    for (const node of attrNodes) {
      addId(node.getAttribute('href') || '');
      addId(node.getAttribute('data-row-key') || '');
      addId(node.getAttribute('data-testid') || '');
      addId(node.getAttribute('data-goods-id') || '');
      addId(node.getAttribute('data-id') || '');
      const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
      if (/商品ID|商品id|商品编号/.test(text)) addId(text);
      if (ids.size >= 1000) break;
    }
    return Array.from(ids);
  }

  function extractBlockProductIds() {
    const ids = new Set();
    const blockNodes = Array.from(document.querySelectorAll(
      'span[class*="id"],div[class*="id"],td[class*="id"],span[id*="id"],div[id*="id"],td[id*="id"]'
    ));
    const addFromText = text => {
      const normalized = String(text || '').replace(/\s+/g, ' ').trim();
      if (!normalized) return;
      const labeledMatches = [
        ...normalized.matchAll(/(?:商品ID|商品id|商品编号|ID)[:：]?\s*(\d{6,})/g)
      ];
      for (const match of labeledMatches) ids.add(match[1]);
      if (/^\d{6,}$/.test(normalized)) ids.add(normalized);
    };

    for (const node of blockNodes) {
      const attrText = [
        node.id || '',
        typeof node.className === 'string' ? node.className : ''
      ].join(' ');
      if (!/(?:^|\s)id[-_]?\d+(?:\s|$)/.test(attrText)) continue;
      addFromText(node.innerText || node.textContent || '');

      const parentText = node.parentElement ? (node.parentElement.innerText || '') : '';
      if (parentText && parentText.length < 500) addFromText(parentText);
      if (ids.size >= 1000) break;
    }
    return Array.from(ids);
  }

  function extractProductBlocks() {
    const seen = new Set();
    const blocks = [];
    const idPattern = /(?:\u5546\u54c1ID|\u5546\u54c1id|\u5546\u54c1\u7f16\u53f7|ID)[:\uff1a]?\s*(\d{6,})/;
    const directIdPattern = /^\d{6,}$/;
    const blockNodes = Array.from(document.querySelectorAll(
      'span[class*="id"],div[class*="id"],td[class*="id"],span[id*="id"],div[id*="id"],td[id*="id"]'
    ));

    const getText = node => (node && (node.innerText || node.textContent) || '').replace(/\s+/g, ' ').trim();
    const getLines = text => String(text || '').split(/\n+/).map(x => x.trim()).filter(Boolean);
    const findImage = container => {
      const img = container ? container.querySelector('img') : null;
      return img ? (img.currentSrc || img.src || img.getAttribute('src') || '') : '';
    };
    const findPrice = text => {
      const match = String(text || '').match(/[￥¥]\s*([0-9]+(?:\.[0-9]{1,2})?)/);
      return match ? match[0].replace(/\s+/g, '') : '';
    };
    const findSpecs = text => {
      const lines = getLines(text);
      const specInfo = [];
      const specCodes = [];
      const specPrices = [];
      for (const line of lines) {
        if (/\u89c4\u683c|\u7f16\u7801|SKU|sku|[￥¥]/.test(line)) {
          if (/\u89c4\u683c/.test(line)) specInfo.push(line);
          const codeMatch = line.match(/(?:\u7f16\u7801|SKU|sku)[:\uff1a]?\s*([A-Za-z0-9_-]{3,})/);
          if (codeMatch) specCodes.push(codeMatch[1]);
          const priceMatch = line.match(/[￥¥]\s*([0-9]+(?:\.[0-9]{1,2})?)/);
          if (priceMatch) specPrices.push(priceMatch[0].replace(/\s+/g, ''));
        }
      }
      return {
        spec_info: Array.from(new Set(specInfo)).slice(0, 8).join(' | '),
        spec_code: Array.from(new Set(specCodes)).slice(0, 20).join(' | '),
        spec_price: Array.from(new Set(specPrices)).slice(0, 20).join(' | ')
      };
    };
    const findTitle = text => {
      const lines = getLines(text);
      for (const line of lines) {
        if (idPattern.test(line) || directIdPattern.test(line)) continue;
        if (/[￥¥]|\u4ef7\u683c|\u89c4\u683c|\u7f16\u7801|\u5728\u552e|\u5df2\u552e/.test(line)) continue;
        if (line.length >= 6 && line.length <= 120) return line;
      }
      return '';
    };
    const scoreContainer = (node, productId) => {
      if (!node) return -1;
      const text = getText(node);
      if (!text || !text.includes(productId)) return -1;
      let score = 0;
      if (node.matches && node.matches('tr')) score += 10;
      if (node.querySelector && node.querySelector('img')) score += 8;
      if (findPrice(text)) score += 6;
      if (findTitle(text)) score += 6;
      if (text.length > 60) score += 4;
      if (text.length > 150) score += 4;
      if (text.length > 3000) score -= 20;
      score += Math.min(6, node.querySelectorAll ? node.querySelectorAll('a,button,img,span,div,td').length / 10 : 0);
      return score;
    };
    const chooseProductContainer = (idNode, productId) => {
      const candidates = [];
      const row = idNode.closest ? idNode.closest('tr') : null;
      if (row) candidates.push(row);
      let node = idNode;
      for (let i = 0; node && i < 9; i += 1) {
        candidates.push(node);
        node = node.parentElement;
      }
      let best = idNode;
      let bestScore = -1;
      for (const candidate of candidates) {
        const score = scoreContainer(candidate, productId);
        if (score > bestScore) {
          best = candidate;
          bestScore = score;
        }
      }
      return best || idNode;
    };

    for (const idNode of blockNodes) {
      const attrText = [idNode.id || '', typeof idNode.className === 'string' ? idNode.className : ''].join(' ');
      if (!/(?:^|\s)id[-_]?\d+(?:\s|$)/.test(attrText)) continue;

      let productId = '';
      const ownText = getText(idNode);
      let match = ownText.match(idPattern);
      if (match) productId = match[1];
      if (!productId && directIdPattern.test(ownText)) productId = ownText;

      let probe = idNode;
      for (let i = 0; probe && i < 6; i += 1) {
        const text = getText(probe);
        match = text.match(idPattern);
        if (!productId && match) productId = match[1];
        if (productId) break;
        probe = probe.parentElement;
      }
      if (!productId || seen.has(productId)) continue;
      seen.add(productId);

      const container = chooseProductContainer(idNode, productId);
      const text = getText(container || idNode);
      const specs = findSpecs(text);
      blocks.push({
        product_id: productId,
        title: findTitle(text),
        image: findImage(container || idNode),
        price: findPrice(text),
        spec_info: specs.spec_info,
        spec_code: specs.spec_code,
        spec_price: specs.spec_price
      });
      if (blocks.length >= 1000) break;
    }
    return blocks;
  }

  function extractCurrentCodeDetail() {
    const isVisible = node => {
      if (!node) return false;
      const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
      const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
      return !!rect && rect.width > 20 && rect.height > 20 && (!style || (style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) !== 0));
    };
    const textOf = node => (node && (node.innerText || node.textContent) || '').replace(/\s+/g, ' ').trim();
    const chooseRoot = () => {
      const selectors = [
        '[role="dialog"]',
        '[aria-modal="true"]',
        '.ant-modal',
        '.ant-drawer',
        '[class*="modal"]',
        '[class*="Modal"]',
        '[class*="drawer"]',
        '[class*="Drawer"]',
        '[class*="dialog"]',
        '[class*="Dialog"]'
      ];
      const candidates = [];
      for (const selector of selectors) {
        for (const node of Array.from(document.querySelectorAll(selector))) {
          if (!isVisible(node)) continue;
          const text = textOf(node);
          if (/(\u89c4\u683c\u4fe1\u606f|\u89c4\u683c).*(\u89c4\u683c\u7f16\u7801|\u7f16\u7801)|(\u89c4\u683c\u7f16\u7801|\u7f16\u7801).*(\u89c4\u683c\u4fe1\u606f|\u89c4\u683c)/.test(text)) {
            candidates.push(node);
          }
        }
      }
      if (!candidates.length) {
        for (const node of Array.from(document.querySelectorAll('div,section,main,form')).filter(isVisible)) {
          const text = textOf(node);
          if (text.length > 40 && text.length < 10000 && /(\u89c4\u683c\u4fe1\u606f|\u89c4\u683c)/.test(text) && /(\u89c4\u683c\u7f16\u7801|\u7f16\u7801)/.test(text)) {
            candidates.push(node);
          }
        }
      }
      if (!candidates.length) return null;
      candidates.sort((a, b) => {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        const areaA = ar.width * ar.height;
        const areaB = br.width * br.height;
        return areaA - areaB;
      });
      return candidates[0];
    };
    const root = chooseRoot();
    const rootText = textOf(root);
    if (!root) {
      return {
        product_id: '',
        title: '',
        product_images: [],
        specs: [],
        all_images: [],
        debug_candidates: [],
        react_debug: [],
        root_debug: {
          tag: '',
          class_name: '',
          text: ''
        },
        source: '\u672a\u627e\u5230\u5f53\u524d\u7f16\u7801\u7a97\u53e3DOM'
      };
    }
    const queryAll = selector => Array.from((root || document).querySelectorAll(selector));
    const valueOf = node => {
      if (!node) return '';
      const tag = (node.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return node.value || '';
      return '';
    };
    const richTextOf = node => {
      if (!node) return '';
      const values = [textOf(node)];
      if (valueOf(node)) values.push(valueOf(node));
      if (node.querySelectorAll) {
        for (const el of Array.from(node.querySelectorAll('input,textarea,select,[title],[aria-label],img'))) {
          values.push(valueOf(el));
          values.push(el.getAttribute('title') || '');
          values.push(el.getAttribute('aria-label') || '');
          values.push(el.getAttribute('alt') || '');
          values.push(el.getAttribute('placeholder') || '');
        }
      }
      return values.map(x => String(x || '').trim()).filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
    };
    const controlValuesOf = node => {
      if (!node || !node.querySelectorAll) return [];
      return Array.from(node.querySelectorAll('input,textarea,select'))
        .map(el => String(el.value || '').trim())
        .filter(Boolean);
    };
    const lineList = text => String(text || '').split(/\n+/).map(x => x.trim()).filter(Boolean);
    const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
    const unique = values => Array.from(new Set(values.map(clean).filter(Boolean)));
    const allImages = unique(queryAll('img').map(img => img.currentSrc || img.src || img.getAttribute('src') || ''));
    const visibleDivTexts = queryAll('div,span,p').map(textOf).filter(Boolean);
    const productCard = queryAll('[class*="goodsCard"],[class*="GoodsCard"],[class*="card"],[class*="Card"]')
      .filter(node => /(?:\u5546\u54c1ID|\bID)[:\uff1a]?\s*\d{6,}/.test(textOf(node)))
      .sort((a, b) => {
        const ac = String(a.className || '');
        const bc = String(b.className || '');
        const scoreA = /goodsCard|GoodsCard/.test(ac) ? 0 : 1;
        const scoreB = /goodsCard|GoodsCard/.test(bc) ? 0 : 1;
        if (scoreA !== scoreB) return scoreA - scoreB;
        return textOf(a).length - textOf(b).length;
      })[0] || null;
    const productCardText = textOf(productCard);
    const productCardImgNode = productCard ? productCard.querySelector('img') : null;
    const productCardImage = productCardImgNode ? (productCardImgNode.currentSrc || productCardImgNode.src || productCardImgNode.getAttribute('src') || '') : '';
    const titleFromProductCard = () => {
      if (!productCard) return '';
      const idNode = Array.from(productCard.querySelectorAll('div,span,p'))
        .find(node => /(?:\u5546\u54c1ID|\bID)[:\uff1a]?\s*\d{6,}/.test(textOf(node)));
      if (idNode && idNode.previousElementSibling) {
        const prevText = textOf(idNode.previousElementSibling);
        if (prevText && !/(?:\u5546\u54c1ID|\bID)[:\uff1a]?\s*\d{6,}/.test(prevText)) return prevText;
      }
      if (idNode && idNode.parentElement) {
        const siblingTexts = Array.from(idNode.parentElement.children)
          .filter(node => node !== idNode && !/^(img|svg)$/i.test(node.tagName || ''))
          .map(textOf)
          .filter(t => t && !/(?:\u5546\u54c1ID|\bID)[:\uff1a]?\s*\d{6,}/.test(t));
        if (siblingTexts.length) return siblingTexts[0];
      }
      const leafTexts = Array.from(productCard.querySelectorAll('div,span,p'))
        .filter(node => !node.children || node.children.length === 0)
        .map(textOf)
        .filter(t => t && !/(?:\u5546\u54c1ID|\bID)[:\uff1a]?\s*\d{6,}/.test(t))
        .filter(t => t.length >= 4 && t.length <= 160);
      return leafTexts[0] || '';
    };

    const labelTitlePattern = /(?:\u5546\u54c1\u6807\u9898|\u6807\u9898|\u5546\u54c1\u540d\u79f0)[:\uff1a]\s*([^\n]{6,160})/;
    let title = titleFromProductCard();
    const titleMatch = rootText.match(labelTitlePattern);
    if (!title && titleMatch) title = clean(titleMatch[1]);
    if (!title) {
      const titleCandidates = visibleDivTexts
        .filter(t => /[\u4e00-\u9fa5]/.test(t))
        .filter(t => t.length >= 8 && t.length <= 120)
        .filter(t => !/(\u5546\u54c1ID|\u7f16\u7801|\u4ef7\u683c|\u89c4\u683c|\u5e93\u5b58|\u8fd0\u8d39|\u4e0a\u4f20|\u4fdd\u5b58|\u53d6\u6d88|\u6dfb\u52a0|\u7f16\u8f91|\u786e\u5b9a|\u641c\u7d22|\u8bf7\u8f93\u5165)/.test(t));
      title = titleCandidates.sort((a, b) => b.length - a.length)[0] || '';
    }

    const productIdPatterns = [
      /(?:\u5546\u54c1ID|\u5546\u54c1id|\u5546\u54c1\u7f16\u53f7|goods_id|goodsId)[:\uff1a]?\s*(\d{6,})/,
      /[?&](?:goods_id|goodsId)=(\d{6,})/
    ];
    let productId = '';
    if (productCardText) {
      const cardId = productCardText.match(/(?:\u5546\u54c1ID|\u5546\u54c1id|\u5546\u54c1\u7f16\u53f7|\bID)[:\uff1a]?\s*(\d{6,})/);
      if (cardId) productId = cardId[1];
    }
    for (const pattern of productIdPatterns) {
      if (productId) break;
      const match = rootText.match(pattern);
      if (match) {
        productId = match[1];
        break;
      }
    }

    const priceFromText = text => {
      const value = String(text || '');
      const money = value.match(/[\uffe5\u00a5]\s*([0-9]+(?:\.[0-9]{1,2})?)/);
      if (money) return money[0].replace(/\s+/g, '');
      const labeled = value.match(/(?:\u4ef7\u683c|\u552e\u4ef7|\u62fc\u5355\u4ef7)[:\uff1a]?\s*([0-9]+(?:\.[0-9]{1,2})?)/);
      return labeled ? labeled[1] : '';
    };
    const codeFromText = text => {
      const value = String(text || '');
      const labeled = value.match(/(?:\u89c4\u683c\u7f16\u7801|\u7f16\u7801|SKU|sku)[:\uff1a]?\s*([^\s\n\r]{2,80})/);
      if (labeled) return labeled[1];
      const loose = value.match(/\b([A-Za-z0-9_-]*[A-Za-z_][A-Za-z0-9_-]{2,}|\d{6,})\b/);
      return loose ? loose[1] : '';
    };
    const cleanCodeCellText = text => {
      let value = clean(text || '');
      value = value
        .replace(/^(?:\u89c4\u683c\u7f16\u7801|\u7f16\u7801|SKU|sku)[:\uff1a]?\s*/i, '')
        .replace(/(?:\u8bf7\u8f93\u5165|\u5df2\u8f93\u5165)/g, '')
        .trim();
      const parts = value.split(/\s+/).map(clean).filter(Boolean);
      if (parts.length > 1) {
        const uniqueParts = Array.from(new Set(parts));
        if (uniqueParts.length === 1) return uniqueParts[0];
      }
      return value;
    };
    const isBadCodeCandidate = (value, options = {}) => {
      const text = clean(value || '');
      if (!text) return true;
      const compact = text.replace(/\s+/g, '');
      if (/^(商品编码|商品ID|商品id|商品编号|规格信息|规格|信息|规格编码|编码|当前价|价格|售价|库存|图片|保存|删除|编辑|请输入|已输入)$/.test(compact)) return true;
      if (/^(?:当前价|价格|售价)[:：]?[￥¥]?[0-9]+(?:\.[0-9]{1,2})?$/.test(compact)) return true;
      if (!options.allowShortNumber && /^[￥¥]?[0-9]{1,5}(?:\.[0-9]{1,2})?$/.test(compact)) return true;
      return false;
    };
    const codeFromCodeCell = text => {
      const value = cleanCodeCellText(text);
      return isBadCodeCandidate(value, { allowShortNumber: true }) ? '' : value;
    };
    const tailCodeCandidateFromText = text => {
      const source = clean(text || '').replace(/(\u8bf7\u8f93\u5165|\u5df2\u8f93\u5165)/g, '').trim();
      if (!source) return '';
      const parts = source.split(/\s+/).map(clean).filter(Boolean);
      for (let i = parts.length - 1; i >= 0; i -= 1) {
        const candidate = cleanCodeCellText(parts[i]);
        const hasPriceBeforeCandidate = /(?:\u5f53\u524d\u4ef7|\u4ef7\u683c|\u552e\u4ef7|[\uffe5\u00a5])/.test(parts.slice(0, i).join(' '));
        if (!isBadCodeCandidate(candidate, { allowShortNumber: hasPriceBeforeCandidate })) return candidate;
      }
      return '';
    };
    const specInfoFromText = text => {
      const isDraftWarningText = value => /(\u8349\u7a3f\u7bb1|\u6b63\u5728\u7f16\u8f91|\u786e\u8ba4\u4fee\u6539\u5f53\u524d\u5546\u54c1\u7f16\u7801|\u81ea\u52a8\u5220\u9664\u8349\u7a3f|\u53bb\u67e5\u770b\u8349\u7a3f)/.test(String(value || ''));
      const isNonSpecLabel = value => {
        const compact = clean(value).replace(/\s+/g, '');
        if (!compact) return true;
        if (isDraftWarningText(compact)) return true;
        if (/^(商品ID|商品id|商品编号|规格编码|编码|当前价|价格|售价|库存|图片|保存|删除|编辑|请输入|已输入)$/.test(compact)) return true;
        if (/^(当前价|价格|售价)[:：]?[￥¥]?[0-9]+(?:\.[0-9]{1,2})?$/.test(compact)) return true;
        return false;
      };
      const lines = lineList(text);
      for (const line of lines) {
        const match = line.match(/(?:\u89c4\u683c\u4fe1\u606f|\u89c4\u683c|\u89c4\u683c\u540d\u79f0)[:\uff1a]?\s*(.{1,120})/);
        if (match) {
          const value = clean(match[1]).replace(/(?:\u5f53\u524d\u4ef7|\u4ef7\u683c|\u552e\u4ef7)[:\uff1a]?\s*[\uffe5\u00a5]?\s*[0-9]+(?:\.[0-9]{1,2})?.*$/, '').trim();
          if (value && !/^\d+$/.test(value) && !isNonSpecLabel(value)) return value;
        }
      }
      for (const line of lines) {
        const value = clean(line).replace(/(?:\u5f53\u524d\u4ef7|\u4ef7\u683c|\u552e\u4ef7)[:\uff1a]?\s*[\uffe5\u00a5]?\s*[0-9]+(?:\.[0-9]{1,2})?.*$/, '').trim();
        if (value.length >= 2 && value.length <= 80 && /[\u4e00-\u9fa5A-Za-z]/.test(value)) {
          if (!isNonSpecLabel(value)) return value;
        }
      }
      return '';
    };
    const firstImageIn = node => {
      const img = node ? node.querySelector('img') : null;
      return img ? (img.currentSrc || img.src || img.getAttribute('src') || '') : '';
    };
    const imagesIn = node => unique(Array.from(node && node.querySelectorAll ? node.querySelectorAll('img') : []).map(img => img.currentSrc || img.src || img.getAttribute('src') || ''));

    const chooseCodeFromValues = values => {
      for (const value of values) {
        const text = codeFromCodeCell(value);
        if (text && !/^[0-9]+(?:\.[0-9]{1,2})?$/.test(text)) return text;
      }
      return '';
    };
    const choosePriceFromValues = values => {
      for (const value of values) {
        const text = clean(value);
        if (/^\d{6,}$/.test(text)) continue;
        if (/^[0-9]{1,5}(?:\.[0-9]{1,2})?$/.test(text)) return text;
        const parsed = priceFromText(text);
        if (parsed) return parsed;
      }
      return '';
    };
    const chooseSpecInfoFromValues = values => {
      for (const value of values) {
        const text = clean(value);
        if (/(\u8349\u7a3f\u7bb1|\u6b63\u5728\u7f16\u8f91|\u786e\u8ba4\u4fee\u6539\u5f53\u524d\u5546\u54c1\u7f16\u7801|\u81ea\u52a8\u5220\u9664\u8349\u7a3f|\u53bb\u67e5\u770b\u8349\u7a3f)/.test(text)) continue;
        if (text.length >= 1 && text.length <= 120 && /[\u4e00-\u9fa5A-Za-z]/.test(text)) {
          if (!/^[A-Za-z0-9_-]{3,}$/.test(text) && !/^[0-9]+(?:\.[0-9]{1,2})?$/.test(text)) return text;
        }
      }
      return '';
    };
    const fieldMetaOf = el => {
      const pieces = [];
      let node = el;
      for (let i = 0; node && i < 4; i += 1) {
        pieces.push(textOf(node));
        pieces.push(node.getAttribute && (node.getAttribute('class') || ''));
        node = node.parentElement;
      }
      return [
        el.getAttribute('placeholder') || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('title') || '',
        el.getAttribute('name') || '',
        el.getAttribute('id') || '',
        ...pieces
      ].join(' ').replace(/\s+/g, ' ').trim();
    };
    const extractSpecsFromControlSequence = () => {
      const controls = queryAll('input,textarea,select')
        .filter(el => String(el.value || '').trim())
        .map(el => ({
          el,
          value: clean(el.value || ''),
          meta: fieldMetaOf(el),
          image: ''
        }));
      const rows = [];
      let current = {};
      const flush = () => {
        if (current.spec_info || current.spec_code || current.price || current.image) {
          pushSpec(
            { ...current, raw_text: current.raw_text || [current.spec_info, current.spec_code, current.price].filter(Boolean).join(' ') },
            current.node || null,
            current.raw_text || '',
            { source: 'control-sequence' }
          );
        }
        current = {};
      };
      for (const item of controls) {
        const merged = `${item.meta} ${item.value}`;
        const hasCodeMeta = /(\u7f16\u7801|SKU|sku|code)/i.test(item.meta);
        const looksLikeCode = /^\d{6,}(?:[-_][^\s]{1,40})?$/.test(item.value) || /^[A-Za-z0-9][^\s]{2,80}$/.test(item.value);
        const isCode = hasCodeMeta || (!isBadCodeCandidate(item.value) && looksLikeCode && !/^[0-9]+(?:\.[0-9]{1,2})?$/.test(item.value));
        const isPrice = !/^\d{6,}$/.test(item.value) && (/(\u4ef7\u683c|\u552e\u4ef7|price)/i.test(merged) || /^[0-9]{1,5}(?:\.[0-9]{1,2})?$/.test(item.value));
        const isSpec = /(\u89c4\u683c|\u89c4\u683c\u4fe1\u606f|\u89c4\u683c\u540d\u79f0|spec|sku)/i.test(merged) && !isCode && !isPrice;

        if (isSpec && current.spec_info && (current.spec_code || current.price)) flush();
        if (isSpec && !current.spec_info) current.spec_info = item.value;
        else if (isCode && !current.spec_code) current.spec_code = codeFromCodeCell(item.value);
        else if (isPrice && !current.price) current.price = item.value;
        else if (!current.spec_info && /[\u4e00-\u9fa5A-Za-z]/.test(item.value) && item.value.length <= 120) current.spec_info = item.value;
        else if (!current.spec_code && isCode) current.spec_code = codeFromCodeCell(item.value);

        current.raw_text = [current.raw_text, `${item.meta} => ${item.value}`].filter(Boolean).join(' | ');
        current.node = item.el.parentElement || item.el;
        if (current.spec_info && current.spec_code && current.price) flush();
      }
      flush();
      return rows;
    };

    const candidateSet = new Set(queryAll('tr,[role="row"],[class*="sku"],[class*="Sku"],[class*="spec"],[class*="Spec"],[class*="row"],[class*="Row"],div'));
    for (const control of queryAll('input,textarea,select')) {
      let node = control;
      for (let i = 0; node && i < 5; i += 1) {
        candidateSet.add(node);
        node = node.parentElement;
      }
    }
    const candidateNodes = Array.from(candidateSet);
    const specs = [];
    const seenSpecs = new Set();
    const specIndexByCode = new Map();
    const specIndexByName = new Map();
    const debugCandidates = [];
    const normalizeSpecName = value => clean(value || '')
      .replace(/^(?:\u89c4\u683c\u4fe1\u606f|\u89c4\u683c\u7f16\u7801|\u89c4\u683c|\u7f16\u7801)\s+/g, '')
      .replace(/(?:\u5f53\u524d\u4ef7|\u4ef7\u683c|\u552e\u4ef7)[:\uff1a]?\s*[\uffe5\u00a5]?\s*[0-9]+(?:\.[0-9]{1,2})?.*$/, '')
      .trim();
    const specScore = spec => {
      const fields = [spec.spec_info, spec.spec_code, spec.price, spec.image].filter(Boolean).length;
      const rawText = String(spec.raw_text || '');
      const moneyCount = (rawText.match(/[\uffe5\u00a5]\s*[0-9]+(?:\.[0-9]{1,2})?/g) || []).length;
      const codeCount = (rawText.match(/\b(?:\d{6,}|[A-Za-z0-9_-]*[A-Za-z_][A-Za-z0-9_-]{2,})\b/g) || []).length;
      const aggregatePenalty = (moneyCount > 1 || codeCount > 2 || rawText.length > 160) ? 500 : 0;
      const conciseBonus = rawText.length <= 80 ? 80 : rawText.length <= 120 ? 40 : 0;
      return fields * 1000 + conciseBonus - aggregatePenalty;
    };
    const pushSpec = (spec, sourceNode, sourceText, extraDebug = {}) => {
      const rawText = clean(spec.raw_text || sourceText || '').replace(/(\u8bf7\u8f93\u5165|\u5df2\u8f93\u5165)/g, '').trim();
      const normalizedSpec = {
        spec_info: normalizeSpecName(spec.spec_info || ''),
        spec_code: clean(spec.spec_code || ''),
        price: clean(spec.price || ''),
        image: clean(spec.image || ''),
        raw_text: rawText.slice(0, 300)
      };
      const compactSpecName = normalizedSpec.spec_info.replace(/\s+/g, '');
      const compactRawText = rawText.replace(/\s+/g, '');
      if (/(\u8349\u7a3f\u7bb1|\u6b63\u5728\u7f16\u8f91|\u786e\u8ba4\u4fee\u6539\u5f53\u524d\u5546\u54c1\u7f16\u7801|\u81ea\u52a8\u5220\u9664\u8349\u7a3f|\u53bb\u67e5\u770b\u8349\u7a3f)/.test(compactSpecName + compactRawText)) return false;
      if (/^\u5546\u54c1\u7f16\u7801[A-Za-z0-9_-]{3,}(?:\u8bf7\u8f93\u5165|\u5df2\u8f93\u5165)?$/.test(compactRawText)) return false;
      if (/^\u5546\u54c1\u7f16\u7801/.test(compactSpecName) && normalizedSpec.spec_code && !normalizedSpec.price && !normalizedSpec.image) return false;
      if (!normalizedSpec.spec_code && !normalizedSpec.spec_info && !normalizedSpec.price && !normalizedSpec.image) return false;
      if (!normalizedSpec.spec_info && !normalizedSpec.image) return false;
      if (normalizedSpec.spec_code && !normalizedSpec.spec_info && !normalizedSpec.price && !normalizedSpec.image) return false;
      if (!normalizedSpec.spec_code && !normalizedSpec.spec_info) return false;
      if (/^(商品编码|商品编码请输入|规格信息|规格|信息|编码|规格编码|请输入|已输入)$/.test(compactSpecName) && !normalizedSpec.spec_code && !normalizedSpec.price) return false;
      if (!normalizedSpec.spec_code && !normalizedSpec.price && !normalizedSpec.image && /^(商品|规格|编码|请输入|已输入)/.test(compactSpecName)) return false;
      if (/(\u5546\u54c1\u4fe1\u606f|\u6279\u91cf\u4fee\u6539|\u7d2f\u8ba1\u9500\u91cf|\u521b\u5efa\u65f6\u95f4|\u64cd\u4f5c)/.test(normalizedSpec.raw_text)) return false;
      const moneyCount = (rawText.match(/[\uffe5\u00a5]\s*[0-9]+(?:\.[0-9]{1,2})?/g) || []).length;
      const codeCount = (rawText.match(/\b\d{6,}\b/g) || []).length;
      if (moneyCount > 1 && codeCount > 1) return false;
      if (normalizedSpec.spec_code && specIndexByCode.has(normalizedSpec.spec_code)) {
        const index = specIndexByCode.get(normalizedSpec.spec_code);
        if (specScore(normalizedSpec) > specScore(specs[index])) specs[index] = normalizedSpec;
        return false;
      }
      const nameKey = normalizedSpec.spec_info;
      if (nameKey && specIndexByName.has(nameKey)) {
        const index = specIndexByName.get(nameKey);
        if (specScore(normalizedSpec) > specScore(specs[index])) {
          specs[index] = normalizedSpec;
          if (normalizedSpec.spec_code) specIndexByCode.set(normalizedSpec.spec_code, index);
        }
        return false;
      }
      const key = `${normalizedSpec.spec_code}|${normalizedSpec.spec_info}|${normalizedSpec.price}|${normalizedSpec.image}`;
      if (seenSpecs.has(key)) return false;
      seenSpecs.add(key);
      if (normalizedSpec.spec_code) specIndexByCode.set(normalizedSpec.spec_code, specs.length);
      if (nameKey) specIndexByName.set(nameKey, specs.length);
      specs.push(normalizedSpec);
      debugCandidates.push({
        tag: sourceNode && sourceNode.tagName || '',
        class_name: sourceNode && typeof sourceNode.className === 'string' ? sourceNode.className.slice(0, 160) : '',
        text: clean(sourceText || '').slice(0, 500),
        parsed: normalizedSpec,
        ...extraDebug
      });
      return true;
    };

    const tableColumnIndexes = rows => {
      const result = { spec: -1, code: -1, price: -1 };
      const headerRows = rows.slice(0, 8);
      for (const row of headerRows) {
        const cells = Array.from(row.querySelectorAll('th,td,[role="cell"],[role="columnheader"]'));
        if (cells.length < 2) continue;
        const texts = cells.map(cell => richTextOf(cell));
        for (let i = 0; i < texts.length; i += 1) {
          const text = clean(texts[i]).replace(/\s+/g, '');
          if (result.spec < 0 && /规格信息|规格名称|规格$/.test(text)) result.spec = i;
          if (result.code < 0 && /规格编码|编码|SKU|sku/i.test(text)) result.code = i;
          if (result.price < 0 && /当前价|价格|售价/.test(text)) result.price = i;
        }
      }
      return result;
    };
    const extractSpecsFromTables = () => {
      const rows = queryAll('tr,[role="row"]');
      const columnIndexes = tableColumnIndexes(rows);
      for (const row of rows) {
        const cells = Array.from(row.querySelectorAll('th,td,[role="cell"],[role="columnheader"]'));
        if (cells.length < 2) continue;
        const rowText = richTextOf(row);
        if (/^(\u89c4\u683c\u4fe1\u606f\s+\u89c4\u683c\u7f16\u7801|\u89c4\u683c\s+\u7f16\u7801)$/.test(rowText)) continue;
        if (!/(\u89c4\u683c|\u7f16\u7801|SKU|sku|\u4ef7\u683c|\u552e\u4ef7|[\uffe5\u00a5]|\b\d{6,}\b)/.test(rowText) && controlValuesOf(row).length < 1) continue;
        const cellTexts = cells.map(cell => richTextOf(cell));
        const values = controlValuesOf(row);
        const image = firstImageIn(row);
        const textAt = index => index >= 0 && index < cellTexts.length ? cellTexts[index] : '';
        const columnSpec = {
          spec_info: specInfoFromText(textAt(columnIndexes.spec)),
          spec_code: codeFromCodeCell(textAt(columnIndexes.code)),
          price: priceFromText(textAt(columnIndexes.price)),
          image,
          raw_text: rowText
        };
        const hasColumnSpec = columnSpec.spec_info || columnSpec.spec_code || columnSpec.price;
        if (hasColumnSpec) {
          if (!columnSpec.spec_code && (columnSpec.spec_info || columnSpec.price)) {
            columnSpec.spec_code = tailCodeCandidateFromText(rowText);
          }
          pushSpec(columnSpec, row, rowText, {
            source: columnSpec.spec_code ? 'table-column-row' : 'table-column-row-no-code',
            column_indexes: columnIndexes,
            cell_texts: cellTexts.slice(0, 12),
            control_values: values.slice(0, 20),
            tail_code_candidate: tailCodeCandidateFromText(rowText)
          });
          continue;
        }
        const spec = {
          spec_info: '',
          spec_code: '',
          price: '',
          image,
          raw_text: rowText
        };
        for (const cellText of cellTexts) {
          spec.spec_code = spec.spec_code || codeFromText(cellText);
          spec.price = spec.price || priceFromText(cellText);
          spec.spec_info = spec.spec_info || specInfoFromText(cellText);
        }
        spec.spec_code = spec.spec_code || chooseCodeFromValues(values);
        spec.price = spec.price || choosePriceFromValues(values);
        spec.spec_info = spec.spec_info || chooseSpecInfoFromValues(values);
        const tailCodeCandidate = tailCodeCandidateFromText(rowText);
        if (!spec.spec_code && (spec.spec_info || spec.price)) spec.spec_code = tailCodeCandidate;
        pushSpec(spec, row, rowText, {
          source: tailCodeCandidate && spec.spec_code === tailCodeCandidate ? 'table-row-tail-code' : 'table-row',
          cell_texts: cellTexts.slice(0, 12),
          control_values: values.slice(0, 20),
          tail_code_candidate: tailCodeCandidate
        });
      }
    };
    extractSpecsFromTables();
    if (!specs.length) extractSpecsFromControlSequence();

    if (!specs.length) {
      for (const node of candidateNodes) {
        const text = richTextOf(node);
        if (!text || text.length > 1200) continue;
        const controlValues = controlValuesOf(node);
        const hasSpecSignal = /(\u89c4\u683c|\u7f16\u7801|SKU|sku|\u4ef7\u683c|\u552e\u4ef7|[\uffe5\u00a5])/.test(text) || controlValues.length >= 2;
        if (!hasSpecSignal) continue;

        const specCode = codeFromText(text) || chooseCodeFromValues(controlValues);
        const specInfo = specInfoFromText(text) || chooseSpecInfoFromValues(controlValues);
        const price = priceFromText(text) || choosePriceFromValues(controlValues);
        const tailCodeCandidate = tailCodeCandidateFromText(text);
        const image = firstImageIn(node);
        pushSpec(
          { spec_info: specInfo, spec_code: specCode || ((specInfo || price) ? tailCodeCandidate : ''), price, image, raw_text: text },
          node,
          text,
          {
            source: !specCode && tailCodeCandidate ? 'candidate-node-tail-code' : 'candidate-node',
            control_values: controlValues.slice(0, 20),
            tail_code_candidate: tailCodeCandidate
          }
        );
        if (specs.length >= 200) break;
      }
    }

    const collectReactLikeData = () => {
      const results = [];
      const safeSerialize = (value, depth = 0, seen = new WeakSet()) => {
        if (value == null) return value;
        if (typeof value === 'function') return undefined;
        if (typeof value !== 'object') return value;
        if (seen.has(value)) return undefined;
        if (depth > 4) return undefined;
        seen.add(value);
        if (Array.isArray(value)) return value.slice(0, 30).map(item => safeSerialize(item, depth + 1, seen));
        const out = {};
        for (const key of Object.keys(value).slice(0, 80)) {
          if (/^(stateNode|return|child|sibling|alternate|_owner|ref)$/.test(key)) continue;
          try {
            const next = safeSerialize(value[key], depth + 1, seen);
            if (next !== undefined) out[key] = next;
          } catch (e) {}
        }
        return out;
      };
      const maybeSpecObject = obj => {
        if (!obj || typeof obj !== 'object') return;
        const jsonText = JSON.stringify(safeSerialize(obj)).slice(0, 2000);
        if (!/(\u89c4\u683c|\u7f16\u7801|SKU|sku|\u4ef7\u683c|\u552e\u4ef7|spec|sku|price|code)/i.test(jsonText)) return;
        const specCode = codeFromText(jsonText) || (jsonText.match(/"(?:specCode|skuCode|code)"\s*:\s*"([^"]{3,})"/i) || [])[1] || '';
        const price = priceFromText(jsonText) || (jsonText.match(/"(?:price|salePrice|skuPrice)"\s*:\s*"?([0-9]+(?:\.[0-9]{1,2})?)"?/i) || [])[1] || '';
        const specInfo = specInfoFromText(jsonText) || (jsonText.match(/"(?:specName|specInfo|skuName|name)"\s*:\s*"([^"]{1,120})"/i) || [])[1] || '';
        const image = (jsonText.match(/https?:\\?\/\\?\/[^"',\s]+(?:jpg|jpeg|png|webp)/i) || [])[0] || '';
        if (pushSpec({ spec_info: specInfo, spec_code: specCode, price, image, raw_text: jsonText }, null, jsonText, { source: 'react-json' })) {
          results.push(jsonText.slice(0, 500));
        }
      };
      for (const node of queryAll('*').slice(0, 3000)) {
        for (const key of Object.keys(node)) {
          if (key.startsWith('__reactProps') || key.startsWith('__reactFiber') || key.startsWith('__vue')) {
            try { maybeSpecObject(node[key]); } catch (e) {}
          }
        }
      }
      for (const script of queryAll('script').slice(0, 80)) {
        const text = script.textContent || '';
        if (text && /(\u89c4\u683c|\u7f16\u7801|SKU|sku|spec|price|code)/i.test(text)) {
          maybeSpecObject({ script_text: text.slice(0, 20000) });
        }
      }
      return results.slice(0, 20);
    };
    const reactDebug = specs.length ? [] : collectReactLikeData();

    const productImages = unique([productCardImage]).slice(0, 1);
    return {
      product_id: productId,
      title,
      product_images: productImages,
      specs,
      all_images: allImages,
      debug_candidates: debugCandidates.slice(0, 50),
      react_debug: reactDebug,
      root_debug: {
        tag: root && root.tagName || '',
        class_name: root && typeof root.className === 'string' ? root.className.slice(0, 160) : '',
        text: rootText.slice(0, 500)
      },
      source: '\u5f53\u524d\u7f16\u7801\u7a97\u53e3DOM'
    };
  }

  async function extractCurrentCodeDetailWithScroll() {
    const snapshots = [];
    const capture = () => {
      const detail = extractCurrentCodeDetail();
      if (detail && (detail.product_id || (detail.specs || []).length)) snapshots.push(detail);
      return detail;
    };
    const first = capture();
    const firstSpecs = (first && first.specs) || [];
    const needsScrollSampling = firstSpecs.some(spec => {
      return (spec.spec_info || spec.price || spec.image) && !spec.spec_code;
    });
    if (!needsScrollSampling) return first || extractCurrentCodeDetail();

    const isVisible = node => {
      if (!node || !node.getBoundingClientRect) return false;
      const rect = node.getBoundingClientRect();
      const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
      return rect.width > 80 && rect.height > 80 && (!style || (style.display !== 'none' && style.visibility !== 'hidden'));
    };
    const scrollTargets = Array.from(document.querySelectorAll('[role="dialog"],[aria-modal="true"],[class*="modal"],[class*="Modal"],[class*="drawer"],[class*="Drawer"],div,section,main'))
      .filter(node => {
        if (!isVisible(node)) return false;
        if ((node.scrollHeight || 0) <= (node.clientHeight || 0) + 80) return false;
        const text = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
        return /规格/.test(text) && /编码/.test(text);
      })
      .sort((a, b) => (a.getBoundingClientRect().width * a.getBoundingClientRect().height) - (b.getBoundingClientRect().width * b.getBoundingClientRect().height))
      .slice(0, 2);

    for (const target of scrollTargets) {
      const originalTop = target.scrollTop || 0;
      const maxTop = Math.max(0, (target.scrollHeight || 0) - (target.clientHeight || 0));
      const positions = Array.from(new Set([0, Math.floor(maxTop * 0.5), maxTop]));
      for (const position of positions) {
        target.scrollTop = position;
        target.dispatchEvent(new Event('scroll', { bubbles: true }));
        await sleep(80);
        capture();
      }
      target.scrollTop = originalTop;
      target.dispatchEvent(new Event('scroll', { bubbles: true }));
      await sleep(40);
    }

    const base = snapshots[0] || first || extractCurrentCodeDetail();
    const byKey = new Map();
    for (const detail of snapshots) {
      if (!base.product_id && detail.product_id) base.product_id = detail.product_id;
      if (!base.title && detail.title) base.title = detail.title;
      if ((!base.product_images || !base.product_images.length) && detail.product_images) base.product_images = detail.product_images;
      if (detail.all_images) base.all_images = Array.from(new Set([...(base.all_images || []), ...detail.all_images]));
      for (const spec of detail.specs || []) {
        const key = [spec.spec_info || '', spec.price || '', spec.image || ''].join('|');
        const existing = byKey.get(key);
        if (!existing) {
          byKey.set(key, { ...spec });
        } else {
          if (!existing.spec_code && spec.spec_code) existing.spec_code = spec.spec_code;
          if (!existing.price && spec.price) existing.price = spec.price;
          if (!existing.image && spec.image) existing.image = spec.image;
          if ((spec.raw_text || '').length > (existing.raw_text || '').length && spec.spec_code) existing.raw_text = spec.raw_text;
        }
      }
    }
    base.specs = Array.from(byKey.values());
    base.debug_candidates = snapshots.flatMap(item => item.debug_candidates || []).slice(0, 80);
    base.source = `${base.source || '当前编码窗口DOM'} + 滚动采样`;
    return base;
  }

  function extractPageLinkIds() {
    const ids = new Set();
    const nodes = Array.from(document.querySelectorAll('span,a,button,div,[class],[id],[data-id]'));
    for (const node of nodes) {
      const candidates = [
        node.id || '',
        typeof node.className === 'string' ? node.className : '',
        node.getAttribute('data-id') || '',
        node.getAttribute('data-row-key') || '',
        node.getAttribute('data-testid') || ''
      ];
      for (const value of candidates) {
        const text = String(value || '');
        const matches = [
          ...text.matchAll(/(?:^|\s)id[-_]?(\d+)(?:\s|$)/g),
          ...text.matchAll(/(?:^|\s)id(\d+)(?:\s|$)/g)
        ];
        for (const match of matches) ids.add(match[1]);
      }
      if (ids.size >= 1000) break;
    }
    return Array.from(ids);
  }

  const productBlocks = extractProductBlocks();
  const currentCodeDetail = await extractCurrentCodeDetailWithScroll();
  const blockProductIds = productBlocks.length ? productBlocks.map(item => item.product_id) : extractBlockProductIds();
  const productIds = blockProductIds.length ? blockProductIds : extractProductIds();
  const pageLinkIds = extractPageLinkIds();
  const totalPatterns = [
    /共\s*([0-9,]+)\s*(?:条|件|个|款|种)?\s*(?:商品|记录)?/,
    /共计\s*([0-9,]+)\s*(?:条|件|个|款|种)?/,
    /全部商品\s*[（(]?\s*([0-9,]+)\s*[）)]?/,
    /商品总数\s*[:：]?\s*([0-9,]+)/
  ];
  let productTotalCount = null;
  let productCountSource = '';
  for (const pattern of totalPatterns) {
    const match = normalizedText.match(pattern);
    if (match) {
      productTotalCount = Number(match[1].replace(/,/g, ''));
      productCountSource = match[0];
      break;
    }
  }

  let rowCount = 0;
  const tableRows = Array.from(document.querySelectorAll('tbody tr')).filter(row => {
    const text = (row.innerText || '').trim();
    return text && /商品|¥|￥|\d{6,}/.test(text);
  });
  if (tableRows.length > rowCount) rowCount = tableRows.length;

  const productCards = Array.from(document.querySelectorAll('[class*="goods"],[class*="Goods"],[class*="product"],[class*="Product"],[data-testid*="goods"],[data-testid*="product"]')).filter(node => {
    const text = (node.innerText || '').trim();
    return text && text.length > 10 && /商品|ID|¥|￥|\d{6,}/.test(text);
  });
  const uniqueTexts = new Set(productCards.map(node => (node.innerText || '').trim().slice(0, 160)));
  if (uniqueTexts.size > rowCount && uniqueTexts.size <= 200) rowCount = uniqueTexts.size;

  const idMatches = normalizedText.match(/(?:商品ID|商品编号|ID)[:：]?\s*\d{6,}/g) || [];
  if (idMatches.length > rowCount) rowCount = idMatches.length;

  const productVisibleCount = rowCount > 0 ? rowCount : null;
  return {
    body_text: bodyText,
    price_links: priceLinks,
    is_goods_list: isGoodsList,
    on_sale_count: onSale.count,
    on_sale_source: onSale.source,
    product_ids: productIds,
    block_product_ids: blockProductIds,
    product_blocks: productBlocks,
    current_code_detail: currentCodeDetail,
    page_link_ids: pageLinkIds,
    product_total_count: productTotalCount,
    product_visible_count: productVisibleCount,
    product_count_source: productCountSource
  };
})()
"""
        try:
            with DevToolsWebSocket(websocket_url, timeout=3) as ws:
                result = ws.call("Runtime.evaluate", {"expression": script, "returnByValue": True, "awaitPromise": True})
                value = result.get("result", {}).get("value", {})
                return value if isinstance(value, dict) else {"body_text": "", "price_links": []}
        except Exception as exc:
            return {"body_text": f"页面读取失败: {exc}", "price_links": []}

    def _evaluate_price_management_page(self, websocket_url):
        if not websocket_url:
            return {"body_text": "", "items": [], "is_price_management": False}

        script = r"""
(async () => {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim();
  const linesOf = value => String(value || '').split(/\n+/).map(x => clean(x)).filter(Boolean);
  const moneyValue = value => {
    const text = String(value || '').replace(/,/g, '');
    const match = text.match(/(?:￥|¥)?\s*([0-9]+(?:\.[0-9]{1,2})?)/);
    return match ? match[1] : '';
  };
  const moneyValuesOf = value => {
    const text = String(value || '').replace(/,/g, '');
    return [...text.matchAll(/(?:￥|¥)?\s*([0-9]+(?:\.[0-9]{1,2})?)/g)].map(match => match[1]);
  };
  const productIdOf = value => {
    const text = String(value || '');
    const labeled = text.match(/(?:商品ID|商品id|商品编号|goods_id|goodsId|ID)[:：]?\s*(\d{6,})/);
    if (labeled) return labeled[1];
    const query = text.match(/[?&](?:goods_id|goodsId|goodsIdList)=(\d{6,})/);
    return query ? query[1] : '';
  };
  const classifyPriceTag = tag => {
    const text = clean(tag);
    if (!text || text.includes('拼单价') || text.includes('无优惠')) return '裸价';
    if (text.includes('限量折扣')) return '限时限量购';
    return '营销活动';
  };
  const discountOf = text => {
    const value = clean(text);
    if (!value || /无优惠|暂无优惠|无商家出资/.test(value)) {
      return { coupon_amount: '', new_customer_discount: '' };
    }
    const newCustomerMatch =
      value.match(/(?:新客立减|首件立减)[^0-9￥¥]{0,40}(?:￥|¥)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:元|块)?/) ||
      value.match(/(?:￥|¥)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:元|块)?[^0-9]{0,40}(?:新客立减|首件立减)/);
    const couponMatch =
      /首件立减/.test(value)
        ? null
        : (
          value.match(/(?:优惠券|商品立减券|店铺券|立减券)[^0-9￥¥]{0,40}(?:￥|¥)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:元|块)?/) ||
          value.match(/(?:￥|¥)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:元|块)?[^0-9]{0,40}(?:优惠券|商品立减券|店铺券|立减券)/)
        );
    return {
      coupon_amount: couponMatch ? couponMatch[1] : '',
      new_customer_discount: newCustomerMatch ? newCustomerMatch[1] : ''
    };
  };
  const priceAndTagOf = text => {
    const source = clean(text);
    const price = moneyValue(source);
    let tag = '';
    const lines = linesOf(text);
    if (lines.length > 1) {
      for (const line of lines) {
        if (!moneyValue(line) && !/(券前价|价格|售价)/.test(line)) {
          tag = line;
          break;
        }
      }
    }
    if (!tag) {
      tag = source
        .replace(/券前价|价格|售价|￥|¥|[0-9.,]/g, ' ')
        .replace(/元/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    }
    const known = tag.match(/拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|限时限量购|百亿补贴|秒杀|活动价|搜索池|营销活动/);
    tag = known ? known[0] : '';
    return { price, tag, tag_type: classifyPriceTag(tag) };
  };
  const textOf = node => clean(node && (node.innerText || node.textContent) || '');
  const richTextOf = node => {
    if (!node) return '';
    const values = linesOf(node.innerText || node.textContent || '');
    if (node.querySelectorAll) {
      for (const el of Array.from(node.querySelectorAll('input,textarea,select,[title],[aria-label]'))) {
        values.push(el.value || '');
        values.push(el.getAttribute('title') || '');
        values.push(el.getAttribute('aria-label') || '');
      }
    }
    return values.flatMap(value => linesOf(value)).filter(Boolean).join('\n');
  };
  const imageOf = node => {
    if (!node || !node.querySelector) return '';
    const img = node.querySelector('img');
    return img ? clean(img.currentSrc || img.src || img.getAttribute('src') || '') : '';
  };
  const isVisible = node => {
    if (!node || !node.getBoundingClientRect) return false;
    const rect = node.getBoundingClientRect();
    const style = window.getComputedStyle ? window.getComputedStyle(node) : null;
    return rect.width > 1 && rect.height > 1 && (!style || (style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) !== 0));
  };
  const fireClick = node => {
    if (!node) return false;
    try {
      node.scrollIntoView({ block: 'center', inline: 'center' });
    } catch (e) {}
    try {
      for (const type of ['mouseover', 'mousedown', 'mouseup', 'click']) {
        node.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
      }
      if (typeof node.click === 'function') node.click();
      return true;
    } catch (e) {
      return false;
    }
  };
  const clickExpandAllSpecs = async () => {
    const specHeaders = Array.from(document.querySelectorAll('th,[role="columnheader"]'))
      .filter(node => /规格信息/.test(textOf(node)) && /展开全部|全部展开|查看全部规格/.test(textOf(node)));
    for (const header of specHeaders) {
      const candidates = Array.from(header.querySelectorAll('a,button,[role="button"],span,div'))
        .filter(node => /展开全部|全部展开|查看全部规格/.test(textOf(node)))
        .sort((a, b) => textOf(a).length - textOf(b).length);
      for (const candidate of candidates) {
        const clickable = candidate.closest('a,button,[role="button"]') || candidate;
        if (fireClick(clickable) || fireClick(candidate)) {
          await sleep(1600);
          return 1;
        }
      }
      if (fireClick(header)) {
        await sleep(1600);
        return 1;
      }
    }

    const nodes = Array.from(document.querySelectorAll('button,a,[role="button"],span,div'))
      .filter(isVisible);
    for (const node of nodes) {
      const text = clean([
        node.innerText || node.textContent || '',
        node.getAttribute && (node.getAttribute('title') || ''),
        node.getAttribute && (node.getAttribute('aria-label') || '')
      ].join(' '));
      if (!/(展开全部|全部展开|查看全部规格)/.test(text)) continue;
      if (/(收起|已展开)/.test(text)) continue;
      try {
        const clickable = node.closest('a,button,[role="button"]') || node;
        fireClick(clickable);
        fireClick(node);
        await sleep(1600);
        return 1;
      } catch (e) {
        return 0;
      }
    }
    return 0;
  };
  const clickCollapseSpecs = async () => {
    const nodes = Array.from(document.querySelectorAll('button,a,[role="button"],span,div'))
      .filter(isVisible)
      .filter(node => /收起/.test(textOf(node)));
    let clicked = 0;
    for (const node of nodes.slice(0, 30)) {
      const clickable = node.closest('a,button,[role="button"]') || node;
      if (fireClick(clickable) || fireClick(node)) clicked += 1;
    }
    if (clicked) await sleep(300);
    return clicked;
  };

  const scrollables = Array.from(document.querySelectorAll('div,main,section,[class*="table"],[class*="Table"],[class*="list"],[class*="List"]'))
    .filter(node => node.scrollHeight && node.clientHeight && node.scrollHeight > node.clientHeight + 60)
    .sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight))
    .slice(0, 5);
  let moreSpecClickCount = 0;
  moreSpecClickCount += await clickExpandAllSpecs();
  await sleep(600);
  for (let i = 0; i < 7; i += 1) {
    window.scrollTo(0, document.body.scrollHeight);
    for (const node of scrollables) node.scrollTop = node.scrollHeight;
    await sleep(420);
  }
  window.scrollTo(0, 0);
  for (const node of scrollables) node.scrollTop = 0;
  await sleep(800);

  const bodyText = (document.body && document.body.innerText || '').slice(0, 80000);
  const normalizedText = clean(bodyText);
  const isPriceManagement = /价格管理|券前价|商家出资优惠|单件预估实收/.test(`${document.title || ''} ${location.href} ${normalizedText}`);

  const headerTexts = [];
  const headerNodes = Array.from(document.querySelectorAll('thead th,[role="columnheader"],th'));
  for (const node of headerNodes) headerTexts.push(textOf(node));
  const headerIndex = namePattern => {
    for (let i = 0; i < headerTexts.length; i += 1) {
      if (namePattern.test(headerTexts[i])) return i;
    }
    return -1;
  };
  const idx = {
    product: headerIndex(/商品|链接/),
    spec: headerIndex(/规格/),
    before: headerIndex(/券前价|价格/),
    discount: headerIndex(/商家出资|优惠/),
    receipt: headerIndex(/单件预估实收|预估实收|实收/)
  };
  const combinedPriceHeaderIndex = headerTexts.findIndex(text =>
    /券前价/.test(text) && /商家出资优惠/.test(text) && /单件预估实收/.test(text)
  );
  if (combinedPriceHeaderIndex >= 0) {
    idx.before = combinedPriceHeaderIndex;
    idx.discount = combinedPriceHeaderIndex + 1;
    idx.receipt = combinedPriceHeaderIndex + 2;
    if (idx.spec < 0 && combinedPriceHeaderIndex > 0) idx.spec = combinedPriceHeaderIndex - 1;
  }
  if (idx.receipt >= 0) {
    if (idx.discount < 0 && idx.receipt > 0) idx.discount = idx.receipt - 1;
    if (idx.before < 0 && idx.receipt > 1) idx.before = idx.receipt - 2;
  }
  if (idx.spec < 0 && idx.before > 0) idx.spec = idx.before - 1;

  const productMap = new Map();
  const ensureProduct = (productId, title, image = '') => {
    if (!productId) return null;
    if (!productMap.has(productId)) {
      productMap.set(productId, { product_id: productId, title: clean(title), image: clean(image), specs: [] });
    } else {
      const existing = productMap.get(productId);
      if (title && !existing.title) existing.title = clean(title);
      if (image && !existing.image) existing.image = clean(image);
    }
    return productMap.get(productId);
  };
  const titleFromText = (text, productId) => {
    const lines = linesOf(text);
    for (const line of lines) {
      if (line.includes(productId)) continue;
      if (/(商品ID|券前价|商家出资|单件预估|规格|￥|¥|优惠券|新客立减|拼单价|限量折扣|大促|首页推荐专区|9块9|搜索池|秒杀|无优惠|活动|营销|折扣|预估实收|存在低价风险|低价风险查看)/.test(line)) continue;
      if (/^(?:[0-9]+(?:\.[0-9]{1,2})?\s*)+(?:大促|首页推荐专区|9块9|搜索池|秒杀|无优惠|拼单价|限量折扣|活动|营销|元|$)/.test(line)) continue;
      if (line.length >= 4 && line.length <= 140) return line;
    }
    return '';
  };
  const specNameFromText = text => {
    const source = clean(text);
    const isBadSpecName = value => {
      const text = clean(value);
      if (!text) return true;
      if (/^(ID[:：]?\s*)?\d{6,}$/.test(text)) return true;
      if (/^(商品预览|商品管理|查看活动价记录|设置红线价|修改满\d+件折扣|价格及优惠详情|详情|收起|展开|存在低价风险查看|on|off|--)$/.test(text)) return true;
      if (/存在低价风险|低价风险查看/.test(text)) return true;
      if (/^(商品ID|ID)[:：]?\s*\d{6,}/.test(text)) return true;
      return false;
    };
    const labeled = source.match(/(?:规格名称|规格信息|规格)[:：]?\s*([^￥¥]{1,120}?)(?=\s*(?:券前价|价格|商家出资|单件预估|￥|¥|$))/);
    if (labeled && !isBadSpecName(labeled[1])) return clean(labeled[1]);
    const lines = linesOf(text);
    for (const line of lines) {
      if (isBadSpecName(line)) continue;
      if (/(商品ID|券前价|商家出资|单件预估|优惠券|新客立减|拼单价|限量折扣|大促|首页推荐专区|9块9|搜索池|秒杀|无优惠|活动|营销|折扣|￥|¥|存在低价风险|低价风险查看)/.test(line)) continue;
      if (/^[0-9]+(?:\.[0-9]{1,2})?$/.test(line)) continue;
      if (line.length >= 1 && line.length <= 80 && /[\u4e00-\u9fa5A-Za-z]/.test(line)) return line;
    }
    return '';
  };
  const specNameLinesOf = text => linesOf(text).filter(line => {
    if (!line) return false;
    if (/^(ID[:：]?\s*)?\d{6,}$/.test(line)) return false;
    if (/^(商品预览|商品管理|查看活动价记录|设置红线价|修改满\d+件折扣|价格及优惠详情|详情|收起|展开|存在低价风险查看|on|off|--)$/.test(line)) return false;
    if (/^(商品ID|ID)[:：]?\s*\d{6,}/.test(line)) return false;
    if (/(商品ID|券前价|商家出资|单件预估|优惠券|新客立减|拼单价|限量折扣|大促|首页推荐专区|9块9|搜索池|秒杀|无优惠|活动|营销|折扣|￥|¥|价格|售价|存在低价风险|低价风险查看)/.test(line)) return false;
    if (/^[0-9]+(?:\.[0-9]{1,2})?$/.test(line)) return false;
    return line.length <= 100 && /[\u4e00-\u9fa5A-Za-z]/.test(line);
  }).map(line => {
    const labeled = line.match(/(?:规格名称|规格信息|规格)[:：]\s*(.{1,100})/);
    return clean(labeled ? labeled[1] : line);
  }).filter(Boolean);
  const isPriceLine = line => {
    const text = clean(line);
    if (!text) return false;
    if (!moneyValue(text)) return false;
    if (/券前价|商家出资|单件预估|优惠券|新客立减|无优惠|商品ID|规格|商品预览|商品管理|设置红线价|价格及优惠详情/.test(text)) return false;
    if (/拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|搜索池|秒杀|活动价|营销活动/.test(text)) {
      return /^(?:￥|¥)?\s*[0-9]+(?:\.[0-9]{1,2})?\s*(?:拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|搜索池|秒杀|活动价|营销活动)?$/.test(text);
    }
    return /^(?:￥|¥)?\s*[0-9]+(?:\.[0-9]{1,2})?$/.test(text);
  };
  const priceLinesOf = text => {
    const sourceLines = linesOf(text);
    const lines = [];
    for (let i = 0; i < sourceLines.length; i += 1) {
      const line = sourceLines[i];
      if (!isPriceLine(line)) continue;
      const next = sourceLines[i + 1] || '';
      if (/拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|搜索池|秒杀|活动价|营销活动/.test(next) && !moneyValue(next)) {
        lines.push(`${line} ${next}`);
      } else {
        lines.push(line);
      }
    }
    if (lines.length) return lines;
    const compact = clean(text);
    const matches = [...compact.matchAll(/(?:￥|¥)?\s*[0-9]+(?:\.[0-9]{1,2})?(?:\s*(?:拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|搜索池|秒杀|活动价|营销活动))?/g)];
    return matches.map(match => clean(match[0])).filter(Boolean);
  };
  const discountLinesOf = text => {
    const lines = linesOf(text);
    const result = [];
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      if (/(优惠券|商品立减券|店铺券|立减券|新客立减|首件立减|无优惠|暂无优惠|无商家出资)/.test(line)) {
        const prev = lines[i - 1] || '';
        result.push(moneyValue(prev) && !/(拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|搜索池|秒杀|活动价|营销活动)/.test(prev) ? `${prev} ${line}` : line);
      }
    }
    return result;
  };
  const receiptLinesOf = text => priceLinesOf(text);
  const addSpecsFromCells = (product, specCellText, beforeCellText, discountCellText, receiptCellText, rowText) => {
    const parseCombinedSpecRows = text => {
      const parsed = [];
      const sourceLines = linesOf(text);
      for (let i = 0; i < sourceLines.length; i += 1) {
        const specName = sourceLines[i];
        if (!specNameLinesOf(specName).length) continue;
        let offset = 1;
        while (/存在低价风险|低价风险查看/.test(sourceLines[i + offset] || '')) offset += 1;
        const priceLine = sourceLines[i + offset] || '';
        const tagLine = sourceLines[i + offset + 1] || '';
        const discountAmountLine = sourceLines[i + offset + 2] || '';
        const discountTextLine = sourceLines[i + offset + 3] || '';
        const receiptLine = sourceLines[i + offset + 4] || '';
        if (!isPriceLine(priceLine)) continue;
        if (!/(拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|搜索池|秒杀|活动价|营销活动)/.test(tagLine)) continue;
        const priceSource = `${priceLine} ${tagLine}`;
        const discountSource = /(优惠券|商品立减券|店铺券|立减券|新客立减|首件立减|无优惠|暂无优惠|无商家出资)/.test(discountTextLine)
          ? `${discountAmountLine} ${discountTextLine}`
          : '';
        const receiptSource = moneyValue(receiptLine) ? receiptLine : '';
        parsed.push({
          spec_name: specName,
          price_source: priceSource,
          discount_source: discountSource,
          receipt_source: receiptSource,
          raw_text: sourceLines.slice(i, i + offset + 5).join(' ')
        });
      }
      return parsed;
    };

    const combinedRows = parseCombinedSpecRows(specCellText && beforeCellText ? specCellText : rowText);
    if (combinedRows.length) {
      for (const parsed of combinedRows) {
        const priceInfo = priceAndTagOf(parsed.price_source);
        const discounts = discountOf(parsed.discount_source);
        const finalReceipt = moneyValue(parsed.receipt_source);
        addSpec(product, {
          spec_name: parsed.spec_name,
          before_price: priceInfo.price,
          price_tag: priceInfo.tag,
          price_tag_type: priceInfo.tag_type,
          merchant_discount_text: clean(parsed.discount_source).slice(0, 160),
          coupon_amount: discounts.coupon_amount,
          new_customer_discount: discounts.new_customer_discount,
          final_receipt: finalReceipt,
          raw_text: clean(parsed.raw_text || rowText).slice(0, 500)
        });
      }
      return combinedRows.length;
    }

    const specLines = specNameLinesOf(specCellText);
    const beforeCellMoneyValues = moneyValuesOf(beforeCellText);
    const beforeCellIsCombined = beforeCellMoneyValues.length >= 2
      && /(拼单价|限量折扣|大促搜索池|场景专属|首页推荐专区|9块9|搜索池|秒杀|活动价|营销活动|无优惠|优惠券|新客立减)/.test(beforeCellText);
    const operationCellText = /商品预览|商品管理|查看活动价记录|设置红线价|修改满\d+件折扣|价格及优惠详情/.test(receiptCellText)
      ? ''
      : receiptCellText;
    const beforeLines = beforeCellIsCombined ? [beforeCellText] : priceLinesOf(beforeCellText);
    const discountLines = discountLinesOf(`${beforeCellText}\n${discountCellText}`);
    const receiptLines = beforeCellIsCombined
      ? [beforeCellMoneyValues[beforeCellMoneyValues.length - 1]]
      : receiptLinesOf(operationCellText);
    const rowTextHasOperationArea = /商品预览|商品管理|查看活动价记录|设置红线价|价格及优惠详情/.test(rowText);
    const rowSpecLines = specLines.length ? specLines : (rowTextHasOperationArea ? [] : specNameLinesOf(rowText));
    const count = Math.max(rowSpecLines.length, beforeLines.length, receiptLines.length, 1);
    let added = 0;
    for (let i = 0; i < count; i += 1) {
      const specName = rowSpecLines[i] || (count === 1 ? specNameFromText(specCellText || rowText) : '');
      const beforeSource = beforeLines[i] || beforeLines[0] || beforeCellText || rowText;
      const discountSource = discountLines[i] || discountLines[0] || '';
      const receiptSource = receiptLines[i] || receiptLines[0] || operationCellText || rowText;
      const priceInfo = priceAndTagOf(beforeSource);
      const discounts = discountOf(discountSource);
      const finalReceipt = moneyValue(receiptSource);
      if (!specName || !priceInfo.price) continue;
      addSpec(product, {
        spec_name: specName,
        before_price: priceInfo.price,
        price_tag: priceInfo.tag,
        price_tag_type: priceInfo.tag_type,
        merchant_discount_text: clean(discountSource).slice(0, 160),
        coupon_amount: discounts.coupon_amount,
        new_customer_discount: discounts.new_customer_discount,
        final_receipt: finalReceipt,
        raw_text: clean(rowText).slice(0, 500)
      });
      added += 1;
    }
    return added;
  };
  const addSpec = (product, spec) => {
    if (!product || !spec.spec_name || !spec.before_price) return;
    const key = `${spec.spec_name}|${spec.before_price}|${spec.final_receipt}|${spec.price_tag}`;
    if (product.specs.some(item => `${item.spec_name}|${item.before_price}|${item.final_receipt}|${item.price_tag}` === key)) return;
    product.specs.push(spec);
  };

  let currentProductId = '';
  let currentTitle = '';
  const rowNodes = Array.from(document.querySelectorAll('tbody tr,[role="row"]'));
  for (const row of rowNodes) {
    const cells = Array.from(row.querySelectorAll('td,[role="cell"]'));
    if (cells.length < 2) continue;
    const rowText = richTextOf(row);
    const rowProductId = productIdOf(rowText) || currentProductId;
    if (!rowProductId) continue;
    currentProductId = rowProductId;
    currentTitle = titleFromText(rowText, rowProductId) || currentTitle;
    const cellText = i => i >= 0 && cells[i] ? richTextOf(cells[i]) : '';
    const productCellText = cellText(idx.product);
    const specCellText = cellText(idx.spec);
    const beforeCellText = cellText(idx.before);
    const discountCellText = cellText(idx.discount);
    const receiptCellText = cellText(idx.receipt);
    const product = ensureProduct(rowProductId, titleFromText(productCellText || rowText, rowProductId) || currentTitle, imageOf(cells[idx.product]) || imageOf(row));
    const addedFromCells = addSpecsFromCells(product, specCellText, beforeCellText, discountCellText, receiptCellText, rowText);
    if (!addedFromCells) {
      const priceSource = beforeCellText || rowText;
      const priceInfo = priceAndTagOf(priceSource);
      const discountText = discountCellText || rowText;
      const discounts = discountOf(discountText);
      const finalReceipt = moneyValue(receiptCellText || rowText);
      addSpec(product, {
        spec_name: specNameFromText(specCellText || rowText),
        before_price: priceInfo.price,
        price_tag: priceInfo.tag,
        price_tag_type: priceInfo.tag_type,
        merchant_discount_text: clean(discountText).slice(0, 160),
        coupon_amount: discounts.coupon_amount,
        new_customer_discount: discounts.new_customer_discount,
        final_receipt: finalReceipt,
        raw_text: clean(rowText).slice(0, 500)
      });
    }
  }

  if (!productMap.size) {
    const candidateNodes = Array.from(document.querySelectorAll('[class*="row"],[class*="Row"],[class*="goods"],[class*="Goods"],[class*="product"],[class*="Product"],div'))
      .filter(node => {
        const text = textOf(node);
        return text.length >= 40 && text.length <= 2500 && /\d{6,}/.test(text) && /券前价|单件预估实收|商家出资|拼单价|限量折扣|首页推荐专区|9块9|秒杀|￥|¥/.test(text);
      });
    for (const node of candidateNodes) {
      const text = richTextOf(node);
      const productId = productIdOf(text);
      if (!productId) continue;
      const product = ensureProduct(productId, titleFromText(text, productId), imageOf(node));
      const priceInfo = priceAndTagOf(text);
      const discounts = discountOf(text);
      const receiptMatch = text.match(/(?:单件预估实收|预估实收|实收)[:：]?\s*(?:￥|¥)?\s*([0-9]+(?:\.[0-9]{1,2})?)/);
      addSpec(product, {
        spec_name: specNameFromText(text),
        before_price: priceInfo.price,
        price_tag: priceInfo.tag,
        price_tag_type: priceInfo.tag_type,
        merchant_discount_text: clean(text).slice(0, 160),
        coupon_amount: discounts.coupon_amount,
        new_customer_discount: discounts.new_customer_discount,
        final_receipt: receiptMatch ? receiptMatch[1] : '',
        raw_text: clean(text).slice(0, 500)
      });
    }
  }

  const items = Array.from(productMap.values()).filter(item => item.specs.length);
  const collapseClickCount = await clickCollapseSpecs();
  return {
    body_text: bodyText,
    is_price_management: isPriceManagement,
    visible_rows: rowNodes.length,
    items,
    debug: {
      header_texts: headerTexts.slice(0, 40),
      header_index: idx,
      scrollable_count: scrollables.length,
      more_spec_click_count: moreSpecClickCount,
      collapse_spec_click_count: collapseClickCount
    }
  };
})()
"""
        try:
            with DevToolsWebSocket(websocket_url, timeout=20) as ws:
                result = ws.call(
                    "Runtime.evaluate",
                    {"expression": script, "returnByValue": True, "awaitPromise": True},
                )
                value = result.get("result", {}).get("value", {})
                return value if isinstance(value, dict) else {"body_text": "", "items": [], "is_price_management": False}
        except Exception as exc:
            return {"body_text": f"页面读取失败: {exc}", "items": [], "is_price_management": False}

    def _find_browser(self):
        candidates = [
            os.environ.get("CHROME_PATH"),
            os.environ.get("EDGE_PATH"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return None
