"""Canonical role families used by the InterviewRadar retrieval filter."""


def build_taxonomy() -> dict:
    return {
        "schema_version": "role-taxonomy/1.0",
        "families": {
            "研发与算法": ["后端工程师", "前端工程师", "移动端工程师", "测试工程师", "数据工程师", "算法工程师", "AI工程师", "安全工程师", "DevOps/SRE", "硬件工程师"],
            "产品与设计": ["产品经理", "项目经理", "策略分析", "用户研究", "UX/UI设计", "交互设计", "内容设计"],
            "增长与商业化": ["产品运营", "用户运营", "内容运营", "增长运营", "市场", "品牌", "公关", "广告销售", "商务拓展"],
            "职能与专业服务": ["HR", "招聘", "财务", "法务", "采购", "行政", "客户成功", "咨询"],
            "行业与业务": ["电商", "教育", "游戏", "金融", "物流", "本地生活", "医疗健康", "企业服务"],
        },
        "evidence": [{"company": "字节跳动", "url": "https://jobs.bytedance.com/campus/page-6272Gc", "notes": "官方校招页面覆盖产品运营、商业化与多个 AI/技术方向。"}],
    }
