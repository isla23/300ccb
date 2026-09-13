import json

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context


# =============================================================================
# 原有识别器
# =============================================================================
@AgentServer.custom_recognition("find_smallest_number")
class SmallestNumberRecognition(CustomRecognition):
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:

        param = json.loads(argv.custom_recognition_param or "{}") or {}
        rois = param.get("candidate_rois")
        if not isinstance(rois, list) or not rois:
            return CustomRecognition.AnalyzeResult(
                box=None,
                detail={"error": "candidate_rois 不能为空"},
            )

        res = []

        for roi in rois:
            reco_detail = context.run_recognition(
                "RecognizeNumber",
                argv.image,
                pipeline_override={
                    "RecognizeNumber": {
                        "roi": roi,
                        "only_rec": True,
                    }
                },
            )

            if reco_detail is None or not reco_detail.hit:
                print(f"无法读取到内容 {roi}")
                res.append(None)
                continue

            text = str(reco_detail.best_result.text)
            try:
                number = float(text)
            except ValueError:
                print(f"{text} 不是数字!")
                res.append(None)
                continue

            res.append(number)

        if not res or None in res:
            return CustomRecognition.AnalyzeResult(
                box=None,
                detail={"error": "存在无法读取到内容"},
            )

        min_index = res.index(min(res))
        return CustomRecognition.AnalyzeResult(
            box=rois[min_index],
            detail={"smallest_number": res[min_index]},
        )


# =============================================================================
# 新增：顺序关键字识别器
# =============================================================================
@AgentServer.custom_recognition("SequentialKeywordOcr")
class SequentialKeywordOcr(CustomRecognition):
    """
    按顺序识别关键字列表，命中后自动切换到下一个。
    - 每轮只识别当前尚未命中的第一个关键字；
    - 命中后自动前进到下一个关键字；
    - 后续轮次自动忽略已命中的关键字；
    - 全部命中后返回失败（可触发 on_error 或结束）。

    参数（custom_recognition_param 中的 JSON）：
      roi:      [x, y, w, h]
      keywords: ["鹊", "极"] 或 "鹊,极"
      reset:    bool，是否重置状态（任务开始时设 true 一次）
    """

    # 用于承载 OCR 参数的临时节点名（需在 pipeline 中预定义）
    HELPER_NODE = "SequentialKeywordOcrHelper"

    def __init__(self):
        super().__init__()      # 必须：初始化父类，创建 _handle
        self._states = {}       # {node_name: {"keywords": [...], "index": int}}

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_param(raw):
        """兼容字符串/字典两种 custom_recognition_param 形式。"""
        if raw is None:
            return {}
        if isinstance(raw, str):
            return json.loads(raw) if raw.strip() else {}
        return raw

    @staticmethod
    def _parse_keywords(raw):
        if isinstance(raw, str):
            return [k.strip() for k in raw.split(",") if k.strip()]
        if isinstance(raw, (list, tuple)):
            return [str(k).strip() for k in raw if str(k).strip()]
        return []

    def _get_state(self, node_name, keywords, reset):
        if reset or node_name not in self._states:
            self._states[node_name] = {
                "keywords": list(keywords),
                "index": 0,
            }
        return self._states[node_name]

    # ------------------------------------------------------------------
    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult:

        param = self._parse_param(argv.custom_recognition_param)
        roi = param.get("roi", [0, 0, 0, 0])
        keywords = self._parse_keywords(param.get("keywords", []))
        reset = bool(param.get("reset", False))

        state = self._get_state(argv.node_name, keywords, reset)

        if not state["keywords"]:
            return CustomRecognition.AnalyzeResult(
                box=None, detail={"error": "keywords 不能为空"}
            )

        if state["index"] >= len(state["keywords"]):
            return CustomRecognition.AnalyzeResult(
                box=None, detail={"error": "所有关键字已识别完"}
            )

        target = state["keywords"][state["index"]]

        # 复用 pipeline 中的 helper 节点做 OCR
        reco_detail = context.run_recognition(
            self.HELPER_NODE,
            argv.image,
            pipeline_override={
                self.HELPER_NODE: {
                    "roi": roi,
                    "expected": [target],
                    "only_rec": False,
                }
            },
        )

        if reco_detail is not None and reco_detail.hit:
            state["index"] += 1
            box = None
            try:
                box = (
                    reco_detail.best_result.box
                    if reco_detail.best_result is not None
                    else reco_detail.box
                )
            except Exception:
                box = None

            return CustomRecognition.AnalyzeResult(
                box=box,
                detail={
                    "hit": target,
                    "next": state["keywords"][state["index"]:],
                    "index": state["index"],
                },
            )

        return CustomRecognition.AnalyzeResult(
            box=None,
            detail={"waiting": target, "index": state["index"]},
        )