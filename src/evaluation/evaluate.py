"""
Evaluación comparativa: reglas vs. LLM sobre el corpus sintético.
Genera métricas y guarda resultados en results/.
"""

import json
import sys
import os
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from rules.classifier import classify_clausula
from llm.classifier import classify_clausula_llm, get_client


CORPUS_PATH = Path(__file__).parent.parent.parent / "corpus" / "synthetic_contracts.json"
RESULTS_PATH = Path(__file__).parent.parent.parent / "results"


def load_corpus() -> list[dict]:
    clausulas = []
    with open(CORPUS_PATH, encoding="utf-8") as f:
        contracts = json.load(f)
    for contract in contracts:
        for c in contract["clausulas"]:
            clausulas.append(c)
    return clausulas


def compute_metrics(results: list, method: str) -> dict:
    tp = fp = tn = fn = 0
    cat_correct = cat_total = 0

    for r in results:
        pred_risk = r.es_riesgo_predicho
        real_risk = r.es_riesgo_real
        pred_cat = r.categoria_predicha
        real_cat = r.categoria_real

        if pred_risk and real_risk:
            tp += 1
        elif pred_risk and not real_risk:
            fp += 1
        elif not pred_risk and not real_risk:
            tn += 1
        else:
            fn += 1

        if pred_cat == real_cat:
            cat_correct += 1
        cat_total += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy_risk = (tp + tn) / len(results) if results else 0.0
    accuracy_cat = cat_correct / cat_total if cat_total > 0 else 0.0

    return {
        "method": method,
        "n_clausulas": len(results),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy_riesgo": round(accuracy_risk, 4),
        "accuracy_categoria": round(accuracy_cat, 4),
    }


def per_category_metrics(results: list) -> dict:
    cats = defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    for r in results:
        cat = r.categoria_real
        if r.es_riesgo_predicho and r.es_riesgo_real:
            cats[cat]["tp"] += 1
        elif r.es_riesgo_predicho and not r.es_riesgo_real:
            cats[cat]["fp"] += 1
        elif not r.es_riesgo_predicho and not r.es_riesgo_real:
            cats[cat]["tn"] += 1
        else:
            cats[cat]["fn"] += 1

    out = {}
    for cat, v in cats.items():
        p = v["tp"] / (v["tp"] + v["fp"]) if (v["tp"] + v["fp"]) > 0 else 0.0
        r = v["tp"] / (v["tp"] + v["fn"]) if (v["tp"] + v["fn"]) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        out[cat] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}
    return out


def run_evaluation(use_llm: bool = False, api_key: str | None = None):
    clausulas = load_corpus()
    print(f"Corpus cargado: {len(clausulas)} cláusulas")

    # --- Baseline de reglas ---
    rules_results = [classify_clausula(c) for c in clausulas]
    rules_metrics = compute_metrics(rules_results, "rules")
    rules_per_cat = per_category_metrics(rules_results)

    print("\n=== BASELINE REGLAS ===")
    _print_metrics(rules_metrics)

    output = {
        "rules": {
            "metrics": rules_metrics,
            "per_category": rules_per_cat,
            "predictions": [
                {
                    "id": r.id,
                    "categoria_real": r.categoria_real,
                    "categoria_predicha": r.categoria_predicha,
                    "es_riesgo_real": r.es_riesgo_real,
                    "es_riesgo_predicho": r.es_riesgo_predicho,
                    "patrones_activados": r.patrones_activados,
                }
                for r in rules_results
            ],
        }
    }

    # --- LLM (opcional) ---
    if use_llm:
        client = get_client(api_key)
        if client is None:
            print("\nLLM: cliente no disponible (falta GEMINI_API_KEY o paquete google-genai)")
        else:
            llm_results = []
            for i, c in enumerate(clausulas):
                print(f"  LLM clasificando {i+1}/{len(clausulas)}: {c['id']}...", end=" ", flush=True)
                r = classify_clausula_llm(c, client)
                print("OK" if not r.error else f"ERROR: {r.error[:60]}")
                llm_results.append(r)
                time.sleep(4)  # respetar free tier (20 RPD, ~10 RPM)
            llm_metrics = compute_metrics(llm_results, "llm")
            llm_per_cat = per_category_metrics(llm_results)

            print("\n=== LLM (gpt-4o-mini) ===")
            _print_metrics(llm_metrics)

            total_tokens = sum(r.tokens_usados for r in llm_results)
            print(f"Tokens totales usados : {total_tokens}")

            output["llm"] = {
                "metrics": llm_metrics,
                "per_category": llm_per_cat,
                "total_tokens": total_tokens,
                "predictions": [
                    {
                        "id": r.id,
                        "categoria_real": r.categoria_real,
                        "categoria_predicha": r.categoria_predicha,
                        "es_riesgo_real": r.es_riesgo_real,
                        "es_riesgo_predicho": r.es_riesgo_predicho,
                        "razon": r.razon,
                        "error": r.error,
                    }
                    for r in llm_results
                ],
            }

            print("\n=== COMPARACIÓN ===")
            for metric in ["precision", "recall", "f1", "accuracy_riesgo", "accuracy_categoria"]:
                rv = rules_metrics[metric]
                lv = llm_metrics[metric]
                winner = "LLM" if lv > rv else ("REGLAS" if rv > lv else "EMPATE")
                print(f"  {metric:25s}: Reglas={rv:.4f}  LLM={lv:.4f}  → {winner}")

    RESULTS_PATH.mkdir(exist_ok=True)
    out_path = RESULTS_PATH / "evaluation_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResultados guardados en: {out_path}")
    return output


def _print_metrics(m: dict):
    print(f"  Precision : {m['precision']:.4f}")
    print(f"  Recall    : {m['recall']:.4f}")
    print(f"  F1        : {m['f1']:.4f}")
    print(f"  Acc riesgo: {m['accuracy_riesgo']:.4f}")
    print(f"  Acc categ : {m['accuracy_categoria']:.4f}")
    print(f"  TP={m['tp']} FP={m['fp']} TN={m['tn']} FN={m['fn']}")


if __name__ == "__main__":
    use_llm = "--llm" in sys.argv
    api_key = os.getenv("GEMINI_API_KEY")
    run_evaluation(use_llm=use_llm, api_key=api_key)
