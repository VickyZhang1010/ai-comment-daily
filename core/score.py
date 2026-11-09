# -*- coding: utf-8 -*-
"""议论文「总—分—总」结构判别与打分。

四维打分（满分 100）：
  开篇立论 25 + 主体论证 30 + 结尾收束 20/25 + 体量形态 15
新闻体、讲话全文等直接扣 40 分。

不依赖分词库，用规则 + 字符 n-gram 重合度，保证零外部依赖、可解释。
"""
import re

OPEN_CLAIM = re.compile(
    r"(是.{0,12}的(必然要求|根本保证|根本遵循|关键一招|重要基础|本质要求|前提|基础)"
    r"|关键在于|核心在于|本质上是|说到底|归根到底"
    r"|(必须|应当|需要|唯有|只有|要)(以|把|坚持|不断|始终|真正|善于)?"
    r"|这启示我们|实践证明|历史和实践|经验告诉我们|不难发现|事实表明)"
)

# 分论点常以"主语 + 要/必须…"开头（如"各地各部门要以案为鉴"），允许前置主语
MODAL_START = re.compile(
    r"^.{0,24}(要|必须|应当|应|需|需要|坚持|着力|重在|关键是|核心是|一方面|另一方面"
    r"|首先|其次|再次|第一|第二|第三|其三|其四|既要|也要|更要)"
)

# 强论点句：明确的价值判断或必要性主张
STRONG_CLAIM = re.compile(
    r"(是.{1,14}的(必然要求|根本保证|根本遵循|关键一招|重要基础|本质要求|前提|基础|底线)"
    r"|关键在于|核心在于|本质上是|说到底|归根到底|根本在于"
    r"|必须|唯有|只有|至关重要|刻不容缓|容不得|不能|决不允许|事关)"
)

# 议论型标题：标题本身就是观点
TITLE_CLAIM = re.compile(
    r"(以.{2,14}(为|促|筑|守|护|谋|求)|让.{2,16}$|筑牢|守护|推动|谱写|开创|答好|走好|打好"
    r"|破解|激活|锻造|擦亮|夯实|何以|岂能|莫让|别让|不能|应当|如何|怎可)"
)

# 短判断句作分论点，如：一体推进"三不腐"，"不敢"是前提。
SHORT_CLAIM = re.compile(r"[^。；]{4,42}(是|在于|重在|难在|贵在|关键在于)[^。；]{2,40}[。；]?$")

# 栏目先验：这些版面/栏目本身就是评论理论，命中加权
CHANNEL_BOOST = ("评论", "时评", "网评", "锐评", "理论", "论坛", "观察",
                 "社论", "评析", "思想", "观点", "声音")

EVIDENCE = re.compile(
    r"(指出|强调|提出|要求|说过|古人云|所谓|《[^》]{2,40}》"
    r"|例如|比如|以.{2,20}为例|近年来|今年以来|曾经|回顾|数据显示"
    r"|多地|有的(地方|单位|干部|人)|一些(地方|单位|干部|人)?|个别|不少"
    r"|\d+(\.\d+)?%|个百分点|亿元|万户|万人次|增长|下降|提升"
    r"|相比|而非|不是.{2,20}而是|既要.{2,20}又要)"
)

CLOSING = re.compile(
    r"(总之|总而言之|综上|最后|因此|可见|唯有|只有.{2,30}才|从而|必将|让我们|新征程"
    r"|归根到底|说到底|一言以蔽之|行而不辍|未来可期|方能|才能.{2,20}"
    r"|站在.{2,20}(起点|节点)|面向未来|长远看)"
)

HEADER_MAX_LEN = 34


def _is_header(para):
    """识别小标题段：短、无句末标点、无逗号、不是连接词开头的正文短句。

    党媒深度评论常用"总—分（小标题1/2/3）—总"结构，小标题是最强的分论点信号。
    """
    p = para.strip()
    if not p or len(p) > HEADER_MAX_LEN or len(p) < 6:
        return False
    if p.endswith(("。", "！", "？", "…", "：", ":", "，", "、")):
        return False
    if p.startswith(("（", "(", "作者", "编辑", "图", "■", "◆")):
        return False
    if re.search(r"[，、]", p):          # 含逗号的通常是正文短句
        return False
    if re.match(r"^(其[一二三四五]|首先|其次|再次|最后|然而|但是|因此|所以|可见|当然|不难)", p):
        return False
    return True

NEWS_STYLE = re.compile(
    r"(本报讯|记者从.{2,20}获悉|通讯员|摄影报道|图片新闻|现场直击|会议指出"
    r"|在.{2,20}会议上强调|出席会议并讲话|调研时强调)"
)

# 结构性体裁排除（本身不是议论文）
NON_ESSAY_TITLE = re.compile(
    r"(答记者问|专访|访谈|对话|招聘|公告|启事|征订|目录|直播|视频|图集|组图)"
)


def _ngrams(text, n=2):
    t = re.sub(r"[^\u4e00-\u9fa5]", "", text)
    return set(t[i:i + n] for i in range(len(t) - n + 1))


def _overlap(a, b):
    ga, gb = _ngrams(a), _ngrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / float(min(len(ga), len(gb)))


def _first_sentence(text, limit=60):
    parts = re.split(r"[。！？；]", text)
    for p in parts:
        p = p.strip()
        if len(p) >= 8:
            return p[:limit]
    return text[:limit]


def _has_modal(para):
    """分论点不必在段首，常以分句形式出现（"…。各地各部门要以案为鉴…"）"""
    for clause in re.split(r"[，。；：、]", para[:200]):
        clause = clause.strip()
        if re.match(r"^.{0,12}(要|必须|应当|需|需要|坚持|着力|重在|关键是|核心是"
                    r"|一方面|另一方面|首先|其次|再次|既要|更要)", clause):
            return True
    return False


def _pick_claim(paragraphs):
    """在前三段里找论点句。官媒评论常见"由头—亮观点"，论点可能后置到第二段。"""
    for para in paragraphs[:3]:
        for sent in re.split(r"(?<=[。！？])", para):
            sent = sent.strip()
            if 14 <= len(sent) <= 120 and STRONG_CLAIM.search(sent):
                return sent
    return ""


def score_article(title, paragraphs, cfg=None, channel=""):
    cfg = cfg or {}
    min_chars = cfg.get("min_chars", 700)
    max_chars = cfg.get("max_chars", 3200)

    paras = [p.strip() for p in paragraphs if p.strip()]
    n = len(paras)
    body_text = "".join(paras)
    chars = len(body_text)

    result = {
        "score": 0,
        "is_essay": False,
        "reason": "",
        "char_count": chars,
        "paragraph_count": n,
        "structure": {"opening": "", "claim": "", "points": [], "closing": "", "echo": False},
        "evidence_types": [],
        "dims": {"opening": 0, "body": 0, "closing": 0, "shape": 0},
    }

    if n < 3 or chars < 200:
        result["reason"] = "段落过少，无法构成完整文章结构"
        return result

    # ---------- 开篇立论 ----------
    opening = paras[0]
    claim = _pick_claim(paras)
    title_claim = bool(TITLE_CLAIM.search(title or ""))
    if claim and claim in opening:
        d_open = 25
    elif claim and claim in paras[1]:
        d_open = 20            # 由头式开头，论点后置一段
    elif claim:
        d_open = 14
    elif title_claim:
        d_open = 12            # 标题即观点（如"以务实之举筑牢防火墙"）
    elif len(opening) >= 80:
        d_open = 12            # 有实质内容的总起段（深度评论常见）
    else:
        d_open = 0
    if title_claim and d_open:
        d_open = min(25, d_open + 3)

    # ---------- 小标题结构 ----------
    headers = [p for p in paras[1:-1] if _is_header(p)]
    has_sections = 2 <= len(headers) <= 5

    # ---------- 主体论证 ----------
    body_paras = paras[1:-1] if n >= 4 else paras[1:]
    points = []
    evidence_hits = 0
    ev_types = set()
    for para in body_paras:
        head = para[:45]
        is_short_claim = len(para) <= 46 and bool(SHORT_CLAIM.search(para))
        has_modal = _has_modal(para)
        has_ev = bool(EVIDENCE.search(para))
        if has_ev:
            evidence_hits += 1
            for label, pat in (("引用", r"指出|强调|古人云|《"), ("数据", r"\d+(\.\d+)?%|个百分点|亿元"),
                               ("举例", r"例如|比如|为例|近年来"), ("对比", r"相比|而非|不是.{2,20}而是")):
                if re.search(pat, para):
                    ev_types.add(label)
        if has_modal or has_ev or is_short_claim:
            points.append({
                "index": len(points) + 1,
                "point": _first_sentence(para, 40),
                "text": para,
                "has_evidence": has_ev,
                "short_claim": is_short_claim,
            })

    ev_ratio = (evidence_hits / float(len(body_paras))) if body_paras else 0.0
    if has_sections:
        d_body = 30            # 小标题式分论点，党媒深度评论的标准写法
    elif len(points) >= 2 and ev_ratio >= 0.4:
        d_body = 30
    elif len(points) >= 2:
        d_body = 24
    elif len(points) == 1 and ev_ratio >= 0.4:
        d_body = 16
    else:
        d_body = 6

    # ---------- 结尾收束 ----------
    closing = paras[-1]
    close_hit = bool(CLOSING.search(closing))
    echo = False
    if claim:
        echo = _overlap(opening, closing) >= 0.10 or _overlap(claim, closing) >= 0.08
    else:
        echo = _overlap(opening, closing) >= 0.10
    # 结尾出现明确的收束词，结构上就等于回扣开头
    if not echo and close_hit and re.search(r"(最后|总之|综上|总的来看|总的看)", closing):
        echo = True
    if close_hit and echo:
        d_close = 25
    elif close_hit:
        d_close = 18
    elif echo:
        d_close = 8
    else:
        d_close = 0

    # ---------- 体量形态 ----------
    d_shape = 0
    if min_chars <= chars <= max_chars:
        d_shape += 10
    elif 500 <= chars < min_chars:
        d_shape += 5
    if 4 <= n <= 12:
        d_shape += 5
    elif 13 <= n <= 30:
        d_shape += 4
    elif n == 3 or 31 <= n <= 40:
        d_shape += 2

    total = d_open + d_body + d_close + d_shape

    # ---------- 排除项 ----------
    penalty = 0
    reasons = []
    news_hit = NEWS_STYLE.search(body_text[:400])
    if news_hit:
        penalty += 40
        reasons.append("疑似新闻报道体")
    if NON_ESSAY_TITLE.search(title or ""):
        penalty += 35
        reasons.append("体裁为访谈/公告类")
    if chars < 400:
        penalty += 25
        reasons.append("篇幅过短")

    total = max(0, total - penalty)

    # 栏目先验：评论/理论版面的文章本就是议论文，加权（不越过新闻体排除）
    boost = 0
    if not news_hit and any(k in (channel or "") for k in CHANNEL_BOOST):
        boost = 6
        total = min(98, total + boost)     # 封顶 98，保留区分度

    result.update({
        "score": total,
        "is_essay": total >= 70 and not news_hit,
        "reason": "、".join(reasons) if reasons else ("符合总分总结构" if total >= 70 else "结构特征不足"),
        "structure": {
            "opening": opening,
            "claim": claim or _first_sentence(opening, 60),
            "points": points[:5],
            "closing": closing,
            "echo": bool(echo),
            "headers": headers,
            "sectioned": has_sections,
        },
        "evidence_types": sorted(ev_types),
        "dims": {"opening": d_open, "body": d_body, "closing": d_close, "shape": d_shape},
    })
    return result
