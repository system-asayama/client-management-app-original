# -*- coding: utf-8 -*-
"""
comment_generator.py
繁殖意思決定支援システム - コメント・改善提案生成モジュール

重要な設計方針：
- AIに数値計算はさせない
- AIには計算済みJSONだけ渡す
- AIは説明文・改善案・レポート文面だけ作る
- AIなしでもルールベースコメントで動作する
"""
from __future__ import annotations
import os
import json
import logging

logger = logging.getLogger(__name__)


# ===========================================================================
# ルールベースコメント生成（AI不要）
# ===========================================================================

def generate_rule_based_summary(eval_result: dict) -> str:
    """
    計算済み評価結果からルールベースのサマリーコメントを生成する。
    AIなしで動作する。

    Parameters
    ----------
    eval_result : evaluate_mating_compatibility_full の出力 dict

    Returns
    -------
    str: 日本語サマリーコメント
    """
    lines = []

    coi_pct = eval_result.get('coi_percent', 0)
    rank    = eval_result.get('rank', '')
    total   = eval_result.get('total_score', None)
    judgment = eval_result.get('judgment', '')

    # COI コメント
    if coi_pct == 0:
        lines.append('近交係数（COI）は0%で、血統上の共通祖先は確認されていません。')
    elif coi_pct < 5:
        lines.append(f'近交係数（COI）は{coi_pct:.2f}%と低く、血統の多様性が保たれています。')
    elif coi_pct < 10:
        lines.append(f'近交係数（COI）は{coi_pct:.2f}%とやや高い状態です。慎重な確認が必要です。')
    elif coi_pct < 20:
        lines.append(f'近交係数（COI）は{coi_pct:.2f}%と高い状態です。近親交配のリスクが高い可能性があります。')
    else:
        lines.append(f'近交係数（COI）は{coi_pct:.2f}%と非常に高い状態です。この組み合わせは推奨できません。')

    # AVK コメント
    avk = eval_result.get('avk', {})
    if avk:
        avk_pct = avk.get('avk_percent', 100)
        if avk_pct >= 90:
            lines.append(f'祖先多様性（AVK）は{avk_pct}%と高く、血統の多様性が確保されています。')
        elif avk_pct >= 80:
            lines.append(f'祖先多様性（AVK）は{avk_pct}%でやや重複が見られます。')
        elif avk_pct >= 70:
            lines.append(f'祖先多様性（AVK）は{avk_pct}%で重複が多めです。アウトクロスの検討をお勧めします。')
        else:
            lines.append(f'祖先多様性（AVK）は{avk_pct}%と低く、祖先集中が強い状態です。')

    # 遺伝病リスク コメント
    gene_risks = eval_result.get('genetic_disease_risks', [])
    high_risks = [r for r in gene_risks if r.get('risk') in ('very_high', 'high')]
    if high_risks:
        names = '、'.join(r.get('disease_name', '') for r in high_risks[:3])
        lines.append(f'遺伝病リスクが高い可能性のある疾患が検出されました：{names}。交配前に専門家への相談を推奨します。')
    elif gene_risks:
        lines.append('遺伝病リスクは低い状態ですが、引き続き定期的な遺伝子検査をお勧めします。')

    # 健康履歴 コメント
    health = eval_result.get('health_evaluation', {})
    if health.get('health_warnings'):
        lines.append('親犬の健康履歴に注意が必要な項目があります。獣医師への相談を推奨します。')

    # 繁殖履歴 コメント
    breeding = eval_result.get('breeding_evaluation', {})
    if breeding.get('breeding_warnings'):
        lines.append('繁殖履歴に注意が必要な項目があります。')

    # 産子実績 コメント
    offspring = eval_result.get('offspring_evaluation', {})
    perf_level = offspring.get('performance_level', 'unknown')
    if perf_level == 'excellent':
        lines.append('過去の産子実績は良好です。')
    elif perf_level == 'good':
        lines.append('過去の産子実績は概ね良好です。')
    elif perf_level == 'fair':
        lines.append('過去の産子実績にやや懸念があります。')
    elif perf_level == 'poor':
        lines.append('過去の産子実績に問題が見られます。同じ組み合わせの再交配は慎重に判断してください。')

    # 総合判定
    if total is not None:
        lines.append(f'総合スコアは{total}点（100点満点）で、判定は「{judgment}」です。')

    return ''.join(lines)


def generate_rule_based_improvements(eval_result: dict) -> list[str]:
    """
    計算済み評価結果から改善提案リストをルールベースで生成する。

    Returns
    -------
    list of str: 改善提案リスト
    """
    suggestions = list(eval_result.get('improvement_suggestions', []))

    coi_pct = eval_result.get('coi_percent', 0)
    avk     = eval_result.get('avk', {})
    line_dep = eval_result.get('line_dependency', {})
    breed_risks = eval_result.get('breed_risk_evaluation', {})
    offspring = eval_result.get('offspring_evaluation', {})
    breeding = eval_result.get('breeding_evaluation', {})
    concentration = eval_result.get('ancestor_concentration', [])

    # COI 改善提案
    if coi_pct >= 10:
        suggestions.append(f'COIを5%未満に下げる候補を比較してください（現在{coi_pct:.2f}%）。')

    # AVK 改善提案
    if avk.get('avk_percent', 100) < 80:
        suggestions.append('同一ラインへの依存が高いため、アウトクロス候補を検討してください。')

    # ライン依存度 改善提案
    if line_dep.get('dependency_level') in ('high', 'very_high'):
        top = line_dep.get('top_ancestor', '')
        if top:
            suggestions.append(f'共通祖先「{top}」を含まない候補を検討してください。')

    # 高度集中祖先 改善提案
    high_conc = [a for a in concentration if a.get('concentration_level') == 'high']
    for a in high_conc[:2]:
        suggestions.append(f'祖先「{a["name"]}」が{a["appearance_count"]}回出現しています。血統の多様化を検討してください。')

    # 犬種別検査 改善提案
    missing = breed_risks.get('missing_tests', [])
    for m in missing[:3]:
        side_label = '父犬' if m.get('side') == 'sire' else '母犬'
        suggestions.append(f'{side_label}の{m["risk_name"]}検査（{m["recommended_test"]}）が未実施です。交配前に検査してください。')

    # 産子実績 改善提案
    if offspring.get('performance_level') == 'poor':
        suggestions.append('過去産子の疾患発生率が高いため、同じ組み合わせの再交配は慎重に判断してください。')

    # 繁殖履歴 改善提案
    dam_stats = breeding.get('dam_stats', {})
    if dam_stats.get('total_litters', 0) >= 5:
        suggestions.append(f'母犬の出産回数が{dam_stats["total_litters"]}回と多いため、繁殖休止を検討してください。')

    # 重複除去
    seen = set()
    unique = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    return unique


# ===========================================================================
# AI コメント生成（OpenAI API 使用）
# ===========================================================================

def generate_ai_comment_full(eval_result: dict) -> str:
    """
    計算済み評価結果を AI に渡してコメントを生成する。

    重要：
    - AI には計算済みの JSON のみ渡す
    - AI は数値計算を行わない
    - AI は説明文・改善案・レポート文面のみ生成する
    - AI が利用できない場合はルールベースにフォールバックする

    獣医学的な断定は避け、「リスクが高い可能性」「慎重な確認が必要」
    などの表現を使うよう指示する。

    Returns
    -------
    str: AI 生成コメント（失敗時はルールベースコメント）
    """
    try:
        from openai import OpenAI
        client = OpenAI()

        # AI に渡す計算済みサマリー（数値はすべて計算済み）
        summary_data = {
            'coi_percent': eval_result.get('coi_percent', 0),
            'coi_rank': eval_result.get('rank', ''),
            'avk_percent': eval_result.get('avk', {}).get('avk_percent', 0),
            'avk_diversity_level': eval_result.get('avk', {}).get('diversity_level', ''),
            'total_score': eval_result.get('total_score', 0),
            'judgment': eval_result.get('judgment', ''),
            'judgment_level': eval_result.get('judgment_level', ''),
            'genetic_disease_risks': [
                {
                    'disease_name': r.get('disease_name', ''),
                    'risk': r.get('risk', ''),
                    'risk_label': r.get('risk_label', ''),
                }
                for r in eval_result.get('genetic_disease_risks', [])
            ],
            'close_inbreeding_patterns': eval_result.get('close_inbreeding_patterns', []),
            'health_warnings': eval_result.get('health_evaluation', {}).get('health_warnings', []),
            'breeding_warnings': eval_result.get('breeding_evaluation', {}).get('breeding_warnings', []),
            'offspring_performance_level': eval_result.get('offspring_evaluation', {}).get('performance_level', 'unknown'),
            'breed_warnings': eval_result.get('breed_risk_evaluation', {}).get('breed_warnings', []),
            'improvement_suggestions': generate_rule_based_improvements(eval_result),
            'forced_deductions': eval_result.get('forced_deductions', []),
        }

        prompt = f"""あなたは犬の繁殖専門家のアシスタントです。
以下の交配評価データ（すべて計算済みの数値）をもとに、ブリーダー向けの評価コメントを日本語で作成してください。

【重要な制約】
- 数値の再計算は行わないこと
- 「必ず安全」「必ず危険」などの断定表現は使わないこと
- 「リスクが高い可能性があります」「慎重な確認が必要です」などの表現を使うこと
- 獣医師への相談を促す表現を適切に含めること
- 200〜300文字程度の簡潔なコメントにすること

【評価データ】
{json.dumps(summary_data, ensure_ascii=False, indent=2)}

コメント："""

        response = client.chat.completions.create(
            model='gpt-4.1-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=400,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f'AI コメント生成に失敗しました（ルールベースにフォールバック）: {e}')
        return generate_rule_based_summary(eval_result)


def generate_ai_report_text(eval_result: dict) -> dict:
    """
    繁殖評価レポート用のAI生成テキストを返す。

    Returns
    -------
    dict:
        summary     : str  総合サマリー
        detail      : str  詳細説明
        improvements : list 改善提案
        caution     : str  注意事項
    """
    improvements = generate_rule_based_improvements(eval_result)

    try:
        from openai import OpenAI
        client = OpenAI()

        summary_data = {
            'coi_percent': eval_result.get('coi_percent', 0),
            'total_score': eval_result.get('total_score', 0),
            'judgment': eval_result.get('judgment', ''),
            'avk_percent': eval_result.get('avk', {}).get('avk_percent', 0),
            'genetic_disease_risks': [r.get('disease_name', '') for r in eval_result.get('genetic_disease_risks', []) if r.get('risk') in ('high', 'very_high')],
            'all_warnings': eval_result.get('warnings', [])[:5],
        }

        prompt = f"""犬の繁殖評価レポートの本文を作成してください。
以下の計算済みデータをもとに、ブリーダー向けの専門的な説明文を日本語で作成してください。

【制約】
- 断定表現（「必ず安全」「必ず危険」）は使わないこと
- 「可能性があります」「慎重な確認が必要です」などの表現を使うこと
- 獣医師への相談を促す表現を含めること

【データ】
{json.dumps(summary_data, ensure_ascii=False, indent=2)}

以下のJSON形式で返してください：
{{
  "summary": "総合サマリー（100文字程度）",
  "detail": "詳細説明（200文字程度）",
  "caution": "注意事項（100文字程度）"
}}"""

        response = client.chat.completions.create(
            model='gpt-4.1-mini',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=600,
            temperature=0.7,
            response_format={'type': 'json_object'},
        )
        ai_text = json.loads(response.choices[0].message.content)
        return {
            'summary': ai_text.get('summary', generate_rule_based_summary(eval_result)),
            'detail': ai_text.get('detail', ''),
            'improvements': improvements,
            'caution': ai_text.get('caution', '本評価は参考情報です。最終的な交配判断は必ず獣医師にご相談ください。'),
        }

    except Exception as e:
        logger.warning(f'AI レポートテキスト生成に失敗しました（ルールベースにフォールバック）: {e}')
        return {
            'summary': generate_rule_based_summary(eval_result),
            'detail': '',
            'improvements': improvements,
            'caution': '本評価は参考情報です。最終的な交配判断は必ず獣医師にご相談ください。',
        }
