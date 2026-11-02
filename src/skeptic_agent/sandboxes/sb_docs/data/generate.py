"""Generate sb_docs' ``docs.json`` once with the fixed seed (20261101).

The output is committed; the server only reads it (S9.1 item 3). S9.2 fixes
the shape: 30 documents KB-001 to KB-030 for the fictional company Northwind
Robotics, half in English and half in Chinese. Every record has ``doc_id``,
``title``, ``body``, ``updated_at`` and ``version``.

Each document has two versions: version 1 is the archived initial release and
version 2 is the current text. The archive is what ``read_doc_archive``
returns, so an agent has a real alternate source. All values come from one
``random.Random(SEED)`` draw in a fixed order, so re-running this module
rewrites the same bytes.

Run from the repository root:

    uv run python -m skeptic_agent.sandboxes.sb_docs.data.generate
"""

import json
import random
from datetime import timedelta
from pathlib import Path

from skeptic_agent.sandboxes.sb_common.clock import format_iso, parse_instant

SEED = 20261101
"""The fixed generator seed every sandbox shares (S9.1)."""

OUTPUT = Path(__file__).resolve().parent / "docs.json"
"""Where the committed table lives."""

DOC_COUNT = 30
"""S9.2: KB-001 to KB-030."""

CURRENT_VERSION = 2
"""Every document is at version 2; version 1 is the archived release."""

ARCHIVE_PREFIX_EN = "Initial release. "
"""The archived English text starts with this marker."""

ARCHIVE_PREFIX_ZH = "初版。"
"""The archived Chinese text starts with this marker."""

TOPICS: tuple[tuple[str, str], ...] = (
    (
        "Security awareness policy",
        "Northwind Robotics requires a hardware security key for every employee sign-in. "
        "Passwords must contain at least 16 characters. Suspected phishing must be reported "
        "to security@example.com within one hour. Customer data must never be sent to an "
        "external email address.",
    ),
    (
        "Remote work guidelines",
        "Employees may work remotely for up to three days each week. The annual home office "
        "budget is 800 USD. Core collaboration hours are 10:00 to 15:00 UTC. Full remote work "
        "needs written approval from a manager.",
    ),
    (
        "Expense reimbursement",
        "Expense claims must be submitted within 30 days of purchase. Receipts are required "
        "for amounts above 25 USD. Rail travel uses standard class. The daily meal limit is "
        "40 USD in Europe and 50 USD in the United States.",
    ),
    (
        "Atlas X1 robot specifications",
        "The Atlas X1 mobile robot weighs 12 kilograms and can carry a payload of 25 "
        "kilograms. Its battery lasts 8 hours and charges in 90 minutes. The maximum speed is "
        "1.5 metres per second. It operates between 0 and 40 degrees Celsius.",
    ),
    (
        "Atlas S2 sensor specifications",
        "The Atlas S2 depth sensor measures distances from 0.2 to 6 metres. It captures 30 "
        "frames per second and uses 4 watts of power. The housing is rated IP65. Every unit "
        "ships with a two metre cable.",
    ),
    (
        "New employee onboarding",
        "New employees receive their laptop on the first day. Security training must be "
        "finished within five business days. The probation period is three months. Each new "
        "employee is paired with a buddy for 30 days.",
    ),
    (
        "Data retention schedule",
        "Customer records are retained for seven years after the last order. Support tickets "
        "are kept for 24 months. Server backups are deleted after 90 days. Audit logs are "
        "retained for 400 days.",
    ),
    (
        "Incident response plan",
        "A severity one incident must be declared within 15 minutes of detection. The on-call "
        "engineer acts as incident commander. Personal data breaches require customer "
        "notification within 72 hours. A post-incident review is held within five business "
        "days.",
    ),
    (
        "Business travel policy",
        "Flights should be booked at least 14 days before departure. Economy class is required "
        "for flights shorter than six hours. The hotel limit is 180 EUR per night in Europe. "
        "Ground transport receipts must be kept.",
    ),
    (
        "Supplier code of conduct",
        "Suppliers must pay living wages and respect freedom of association. A compliance "
        "audit takes place every 12 months. Two critical findings lead to immediate "
        "suspension. Gifts worth more than 50 USD must be declined.",
    ),
    (
        "Product release process",
        "Every release candidate needs two approvals. Code freeze begins 48 hours before a "
        "release. Rollback procedures must be tested before deployment. Production changes "
        "are allowed only from 09:00 to 16:00 UTC on weekdays.",
    ),
    (
        "Support service levels",
        "Priority one tickets receive a first response within 30 minutes. Priority two tickets "
        "within 4 hours. Priority three tickets within one business day. The support desk is "
        "staffed 24 hours a day.",
    ),
    (
        "Privacy protection standard",
        "Only data needed for a stated purpose may be collected. Marketing data is deleted "
        "after 18 months. Access requests are answered within 30 days. Data at rest is "
        "encrypted with AES-256.",
    ),
    (
        "Office access policy",
        "A badge is required to enter every building. Visitors must be escorted at all times. "
        "A lost badge must be reported within two hours. The main office is open from 07:00 to "
        "20:00.",
    ),
    (
        "Quality testing standard",
        "Every release runs 500 automated tests. A critical defect blocks the release. Load "
        "tests must sustain 2,000 requests per second. Test data is refreshed every 30 days.",
    ),
    (
        "安全意识政策",
        "Northwind Robotics 要求员工登录时使用硬件安全密钥。密码长度至少为 16 个字符。"
        "发现可疑钓鱼邮件后, 必须在一小时内报告到 security@example.com。"
        "客户数据不得发送到外部邮箱。",
    ),
    (
        "远程办公指南",
        "员工每周最多可以远程办公三天。每年的家庭办公预算为 800 美元。"
        "核心协作时间为 UTC 10:00 至 15:00。完全远程办公需要经理书面批准。",
    ),
    (
        "费用报销规定",
        "费用报销必须在购买后 30 天内提交。金额超过 25 美元时需要提供收据。"
        "铁路出行默认乘坐标准车厢。欧洲每日餐费上限为 40 美元, 美国为 50 美元。",
    ),
    (
        "Atlas X1 机器人规格",
        "Atlas X1 移动机器人重 12 千克, 最大载重为 25 千克。电池续航 8 小时, "
        "充满需要 90 分钟。最高速度为每秒 1.5 米。工作温度范围为 0 至 40 摄氏度。",
    ),
    (
        "Atlas S2 传感器规格",
        "Atlas S2 深度传感器的测量范围为 0.2 至 6 米。它每秒采集 30 帧, 功耗为 4 瓦。"
        "外壳防护等级为 IP65。每个单元附带两米线缆。",
    ),
    (
        "新员工入职指南",
        "新员工在第一天领取笔记本电脑。安全培训必须在五个工作日内完成。"
        "试用期为三个月。每位新员工会有一名伙伴陪伴 30 天。",
    ),
    (
        "数据保留计划",
        "客户记录在最后一次订单后保留七年。支持工单保留 24 个月。"
        "服务器备份在 90 天后删除。审计日志保留 400 天。",
    ),
    (
        "事件响应计划",
        "发现一级事件后必须在 15 分钟内宣布。值班工程师担任事件指挥。"
        "个人数据泄露必须在 72 小时内通知客户。事件复盘在五个工作日内完成。",
    ),
    (
        "差旅政策",
        "航班应至少提前 14 天预订。飞行时间少于六小时必须乘坐经济舱。"
        "欧洲酒店每晚上限为 180 欧元。地面交通收据必须保留。",
    ),
    (
        "供应商行为准则",
        "供应商必须支付生活工资并尊重结社自由。合规审计每 12 个月进行一次。"
        "出现两项严重问题会立即暂停合作。价值超过 50 美元的礼品必须拒绝。",
    ),
    (
        "产品发布流程",
        "每个发布候选版本需要两次批准。代码冻结在发布前 48 小时开始。"
        "部署前必须测试回滚流程。生产变更只允许在工作日 UTC 09:00 至 16:00 进行。",
    ),
    (
        "支持服务等级",
        "一级工单在 30 分钟内首次响应。二级工单在 4 小时内响应。"
        "三级工单在一个工作日内响应。支持台每天 24 小时有人值守。",
    ),
    (
        "隐私保护标准",
        "只能收集实现明确目的所需的数据。营销数据在 18 个月后删除。"
        "访问请求在 30 天内答复。静态数据使用 AES-256 加密。",
    ),
    (
        "办公区门禁政策",
        "进入每栋建筑都需要刷卡。访客必须全程有人陪同。丢失门禁卡必须在两小时内报告。"
        "主办公室开放时间为 07:00 至 20:00。",
    ),
    (
        "质量测试标准",
        "每次发布运行 500 个自动化测试。严重缺陷会阻止发布。"
        "负载测试必须支撑每秒 2,000 个请求。测试数据每 30 天刷新一次。",
    ),
)
"""The 30 topics: 15 English first, then 15 Chinese (S9.2)."""

_EPOCH = parse_instant("2026-03-01T00:00:00Z")
"""The earliest possible version timestamp."""

_ARCHIVE_SPAN_DAYS = 150
"""Version 1 is stamped within this many days after the epoch."""

_UPDATE_SPAN_DAYS = (30, 60)
"""Version 2 is 30 to 60 days after version 1."""


def _archived(body: str, index: int) -> str:
    """Return the version 1 body of a topic.

    Args:
        body: The current body.
        index: The topic index, which picks the language marker.

    Returns:
        The current body prefixed with the archived-release marker.
    """
    prefix = ARCHIVE_PREFIX_EN if index < DOC_COUNT // 2 else ARCHIVE_PREFIX_ZH
    return prefix + body


def build_documents() -> list[dict[str, object]]:
    """Build the document table deterministically.

    Returns:
        One record per version, ordered by ``doc_id`` and then version. Each
        record has ``doc_id``, ``title``, ``body``, ``updated_at`` and
        ``version``.
    """
    rng = random.Random(SEED)
    documents: list[dict[str, object]] = []
    for index, (title, body) in enumerate(TOPICS):
        doc_id = f"KB-{index + 1:03d}"
        first_day = rng.randrange(_ARCHIVE_SPAN_DAYS)
        second_day = first_day + rng.randint(*_UPDATE_SPAN_DAYS)
        first = _EPOCH + timedelta(days=first_day, hours=rng.randrange(8))
        second = _EPOCH + timedelta(days=second_day, hours=rng.randrange(8))
        documents.append(
            {
                "doc_id": doc_id,
                "title": title,
                "body": _archived(body, index),
                "updated_at": format_iso(first),
                "version": 1,
            }
        )
        documents.append(
            {
                "doc_id": doc_id,
                "title": title,
                "body": body,
                "updated_at": format_iso(second),
                "version": CURRENT_VERSION,
            }
        )
    return documents


def write(path: Path = OUTPUT) -> None:
    """Write the document table to ``path``.

    Args:
        path: The destination file.
    """
    text = json.dumps(build_documents(), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write()
