# -*- coding: utf-8 -*-
"""Cost-library real-time LAN synchronization organization dialog."""

import base64
import json
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

try:
    from manager.cost_sync_service import CostSyncService
except ImportError:
    from cost_sync_service import CostSyncService


class CostSyncDialog(QDialog):
    def __init__(self, db, main_window=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.main_window = main_window
        self.setWindowTitle("成本库局域网实时同步")
        self.resize(720, 305)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_state)
        self.timer.start(1000)
        self.refresh_state()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.group_label = QLabel("未加入")
        self.group_id_label = QLabel("-")
        self.role_label = QLabel("-")
        self.local_ip_label = QLabel("-")
        self.local_address_label = QLabel("-")
        self.host_label = QLabel("-")
        self.published_label = QLabel("-")
        self.status_label = QLabel("未启用")
        self.status_label.setStyleSheet("font-weight:600;")
        for label in (self.group_id_label, self.local_ip_label, self.local_address_label, self.host_label):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.host_label.setToolTip(
            "通常使用自动发现。失败时填写同一组织内在线电脑的地址，例如 192.168.1.23:48781。"
        )
        form.addRow("组织名称:", self.group_label)
        form.addRow("组织标识:", self.group_id_label)
        form.addRow("这台电脑:", self.role_label)
        form.addRow("本机 IP:", self.local_ip_label)
        form.addRow("本机同步地址:", self.local_address_label)
        form.addRow("手动连接地址:", self.host_label)
        form.addRow("最近一次同步:", self.published_label)
        form.addRow("连接状态:", self.status_label)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        for text, slot in (
            ("创建组织", self.create_group),
            ("加入组织", self.join_group),
            ("复制组织密钥", self.copy_invite),
            ("设置手动连接地址", self.set_host),
            ("退出组织", self.leave_group),
        ):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def state(self):
        return self.db.get_cost_sync_state()

    def refresh_state(self):
        state = self.state()
        joined = bool(state.get("group_id"))
        service = getattr(self.main_window, "cost_sync_service", None)
        self.group_label.setText(state.get("group_name") or "未加入")
        self.group_id_label.setText(str(state.get("group_id") or "-")[:8])
        self.role_label.setText("组织创建电脑" if state.get("role") == "host" else ("组织成员电脑" if joined else "-"))
        local_ip = service.local_ip() if service else CostSyncService.local_ip()
        self.local_ip_label.setText(local_ip)
        self.local_address_label.setText(
            f"{local_ip}:{service.httpd.server_port}" if service and service.httpd else "-"
        )
        self.host_label.setText((state.get("coordinator_host") or "自动发现") if joined else "-")
        published_at = state.get("published_at") or ""
        self.published_label.setText(published_at or "-")
        if not joined:
            text, color = "未启用", "#777"
        elif state.get("role") == "host" and service and service.httpd:
            text, color = "本机同步服务运行中", "#16803c"
        elif service and time.time() - float(getattr(service, "last_contact_at", 0) or 0) < 5:
            text, color = "已连接，正在实时同步", "#16803c"
        elif self.db.get_setting("cost_sync_skip_initial_diff", "0") == "1":
            text, color = "首次同步未完成：未发现组织成员，请填写创建电脑的同步地址", "#b42318"
        else:
            text, color = "等待任意组织成员上线", "#b35c00"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"font-weight:600;color:{color};")

    def _restart_service(self):
        if self.main_window and hasattr(self.main_window, "restart_cost_sync_service"):
            self.main_window.restart_cost_sync_service()

    def create_group(self):
        name, ok = QInputDialog.getText(self, "创建组织", "组织名称:", text="成本库同步组织")
        if not ok:
            return
        payload, _token = CostSyncService.create_invite(name)
        self.db.configure_cost_sync(payload["group_id"], payload["group_name"], "host", payload["secret"], "")
        self.db.publish_cost_sync_snapshot({"schema": 1, "rows": [], "categories": []}, "")
        self.db.set_setting("cost_sync_pending_json", "")
        self.db.set_setting("cost_sync_skip_initial_diff", "0")
        self._restart_service()
        self.refresh_state()
        self.copy_invite()

    def join_group(self):
        token, ok = QInputDialog.getMultiLineText(self, "加入组织", "粘贴组织密钥:")
        if not ok:
            return
        try:
            invite = CostSyncService.parse_invite(token)
        except ValueError as exc:
            QMessageBox.warning(self, "邀请密钥无效", str(exc))
            return
        host, host_ok = QInputDialog.getText(
            self,
            "手动连接组织成员电脑（可选）",
            "通常留空即可自动发现。若自动发现失败，请填写一台已在线组织成员电脑的地址。\n"
            "格式示例：192.168.1.23 或 192.168.1.23:48781",
            QLineEdit.Normal,
            invite.get("host") or "",
        )
        if not host_ok:
            return
        same_group = self.state().get("group_id") == invite["group_id"]
        self.db.configure_cost_sync(
            invite["group_id"], invite["group_name"], "client", invite["secret"], host.strip()
        )
        if not same_group:
            self.db.set_setting("cost_sync_pending_json", "")
            self.db.set_setting("cost_sync_skip_initial_diff", "1")
        self._restart_service()
        self.refresh_state()

    def copy_invite(self):
        state = self.state()
        if not state:
            QMessageBox.information(self, "提示", "请先创建或加入组织")
            return
        payload = {
            "v": 1,
            "group_id": state.get("group_id"),
            "group_name": state.get("group_name") or "成本库同步组织",
            "secret": state.get("secret"),
        }
        service = getattr(self.main_window, "cost_sync_service", None)
        if service and service.httpd:
            payload["host"] = f"{service.local_ip()}:{service.httpd.server_port}"
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        QApplication.clipboard().setText(base64.urlsafe_b64encode(raw).decode("ascii").rstrip("="))
        self.status_label.setText("组织密钥已复制")

    def set_host(self):
        state = self.state()
        if not state:
            return
        host, ok = QInputDialog.getText(
            self,
            "设置手动连接地址",
            "通常留空即可自动发现。若自动发现失败，请填写一台已在线组织成员电脑的地址。\n"
            "格式示例：192.168.1.23 或 192.168.1.23:48781",
            QLineEdit.Normal, state.get("coordinator_host") or "",
        )
        if ok:
            self.db.update_cost_sync_state(coordinator_host=host.strip())
            service = getattr(self.main_window, "cost_sync_service", None)
            if service:
                service.clear_peer_cache()
                service.notify_local_change()
            self.refresh_state()

    def leave_group(self):
        if not self.state():
            return
        if QMessageBox.question(self, "退出组织", "退出后保留本机成本库数据，确定退出吗？") != QMessageBox.Yes:
            return
        self.db.clear_cost_sync_state()
        self.db.set_setting("cost_sync_pending_json", "")
        self.db.set_setting("cost_sync_skip_initial_diff", "0")
        self._restart_service()
        self.refresh_state()


__all__ = ["CostSyncDialog"]
