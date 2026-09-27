"""Transactional e-mail. Provider is configurable: "smtp" works with any SMTP relay (Resend, SES, Postmark…);
"console" only logs and is refused in production (see Settings.check)."""

import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("email")

TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "verify": {
        "vi": ("Xác nhận email của bạn", "Chào bạn,\n\nBấm vào liên kết sau để xác nhận email:\n{link}\n\nLiên kết hết hạn sau 24 giờ."),
        "en": ("Verify your e-mail", "Hi,\n\nConfirm your e-mail address with this link:\n{link}\n\nThe link expires in 24 hours."),
    },
    "login_code": {
        "vi": ("Mã đăng nhập: {code}", "Mã đăng nhập của bạn là {code}\n\nMã hết hạn sau 10 phút. Nếu không phải bạn, hãy bỏ qua email này."),
        "en": ("Your login code: {code}", "Your login code is {code}\n\nIt expires in 10 minutes. If this wasn't you, ignore this e-mail."),
    },
    "reset": {
        "vi": ("Đặt lại mật khẩu", "Có yêu cầu đặt lại mật khẩu cho tài khoản của bạn:\n{link}\n\nLiên kết hết hạn sau 1 giờ. Nếu không phải bạn, hãy bỏ qua email này."),
        "en": ("Reset your password", "Someone asked to reset your password:\n{link}\n\nThe link expires in 1 hour. If this wasn't you, ignore this e-mail."),
    },
    "payment_receipt": {
        "vi": ("Thanh toán thành công", "Cảm ơn bạn! Đã nhận {amount} {currency} cho gói {product}. {credits} credit đã được cộng vào tài khoản.\nMã đơn: {order_code}"),
        "en": ("Payment received", "Thank you! We received {amount} {currency} for {product}. {credits} credits were added to your account.\nOrder: {order_code}"),
    },
    "payment_failed": {
        "vi": ("Thanh toán chưa thành công", "Thanh toán cho đơn {order_code} chưa thành công. Chưa có khoản nào được trừ. Bạn có thể thử lại tại {link}"),
        "en": ("Payment not completed", "Your payment for order {order_code} did not complete. You were not charged. Try again at {link}"),
    },
    "job_completed": {
        "vi": ("Đã dịch xong: {title}", "Chương \"{title}\" đã xong ({done}/{total} trang). Xem và tải về: {link}"),
        "en": ("Translation ready: {title}", "\"{title}\" is done ({done}/{total} pages). Review and download: {link}"),
    },
    "job_failed": {
        "vi": ("Lỗi khi dịch: {title}", "Rất tiếc, chương \"{title}\" chưa dịch được. Credit chưa dùng đã được hoàn lại. Thử lại tại: {link}"),
        "en": ("Translation failed: {title}", "Sorry, \"{title}\" could not be processed. Unused credits were returned. Retry here: {link}"),
    },
    "account_deleted": {
        "vi": ("Tài khoản đã được xóa", "Tài khoản và các tệp của bạn đã được lên lịch xóa. Hồ sơ thanh toán được giữ theo quy định kế toán."),
        "en": ("Account deleted", "Your account and files are scheduled for deletion. Payment records are kept as required for accounting."),
    },
}


def send(to: str, template: str, locale: str = "vi", **ctx) -> None:
    subject, body = TEMPLATES[template].get(locale) or TEMPLATES[template]["en"]
    subject, body = subject.format(**ctx), body.format(**ctx)
    s = get_settings()
    if s.email_provider == "console":
        log.info("email (console) to=%s subject=%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
