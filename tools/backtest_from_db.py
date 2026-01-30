# Roleta Cloud - Backtest Integrado com Database
# Lê dados reais de decisions.db para análise

import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from database import get_repository
from database.models import Decision


def load_decisions(
    session_id: Optional[str] = None,
    hours_back: int = 24,
    action_filter: Optional[str] = None,
    limit: int = 500
) -> List[Decision]:
    """Carrega decisões do banco de dados."""
    repo = get_repository()
    
    start_time = datetime.now() - timedelta(hours=hours_back)
    
    decisions = repo.get_decisions(
        session_id=session_id,
        start_time=start_time,
        final_action=action_filter,
        limit=limit
    )
    
    # Ordenar cronologicamente (mais antigo primeiro)
    return list(reversed(decisions))


def analyze_strategy_performance(decisions: List[Decision]) -> Dict[str, Any]:
    """Analisa performance da estratégia SDA-17."""
    total = len(decisions)
    bets = [d for d in decisions if d.final_action == "APOSTAR"]
    skips = [d for d in decisions if d.final_action == "PULAR"]
    
    hits = [d for d in bets if d.result_hit is True]
    misses = [d for d in bets if d.result_hit is False]
    pending = [d for d in bets if d.result_hit is None]
    
    # Análise de "e se tivéssemos apostado?"
    skips_would_hit = [d for d in skips if d.result_hit is True]
    skips_would_miss = [d for d in skips if d.result_hit is False]
    
    return {
        "total_decisions": total,
        "total_bets": len(bets),
        "total_skips": len(skips),
        "hits": len(hits),
        "misses": len(misses),
        "pending": len(pending),
        "hit_rate": round(len(hits) / len([d for d in bets if d.result_hit is not None]) * 100, 1) 
                   if any(d.result_hit is not None for d in bets) else 0,
        "skip_analysis": {
            "would_have_hit": len(skips_would_hit),
            "would_have_missed": len(skips_would_miss),
            "saved_by_skip": len(skips_would_miss),
            "missed_opportunity": len(skips_would_hit)
        }
    }


def analyze_triple_rate_effectiveness(decisions: List[Decision]) -> Dict[str, Any]:
    """Analisa efetividade do Triple Rate Advisor."""
    # Decisões onde SDA17 recomendou mas TR vetou
    vetoed = [d for d in decisions if d.sda_should_bet and not d.tr_should_bet]
    vetoed_would_hit = [d for d in vetoed if d.result_hit is True]
    vetoed_would_miss = [d for d in vetoed if d.result_hit is False]
    
    # Por nível de confiança
    by_confidence = {}
    for conf in ["alta", "media", "baixa"]:
        conf_decisions = [d for d in decisions if d.tr_confidence == conf and d.final_action == "APOSTAR"]
        conf_hits = [d for d in conf_decisions if d.result_hit is True]
        by_confidence[conf] = {
            "total": len(conf_decisions),
            "hits": len(conf_hits),
            "rate": round(len(conf_hits) / len(conf_decisions) * 100, 1) if conf_decisions else 0
        }
    
    return {
        "vetoed_by_tr": len(vetoed),
        "vetoed_would_hit": len(vetoed_would_hit),
        "vetoed_would_miss": len(vetoed_would_miss),
        "veto_saved_percent": round(len(vetoed_would_miss) / len(vetoed) * 100, 1) if vetoed else 0,
        "by_confidence": by_confidence
    }


def analyze_gale_performance(decisions: List[Decision]) -> Dict[str, Any]:
    """Analisa performance por nível de Gale."""
    by_level = {}
    
    for level in [1, 2, 3]:
        level_bets = [d for d in decisions 
                      if d.gale_level == level and d.final_action == "APOSTAR"]
        level_hits = [d for d in level_bets if d.result_hit is True]
        
        by_level[f"G{level}"] = {
            "total": len(level_bets),
            "hits": len(level_hits),
            "rate": round(len(level_hits) / len(level_bets) * 100, 1) if level_bets else 0
        }
    
    return by_level


def analyze_calibration(decisions: List[Decision]) -> Dict[str, Any]:
    """Analisa efetividade da calibração por offset."""
    by_offset = {}
    
    for d in decisions:
        if d.final_action != "APOSTAR":
            continue
            
        offset = d.calibration_offset
        if offset not in by_offset:
            by_offset[offset] = {"total": 0, "hits": 0}
        
        by_offset[offset]["total"] += 1
        if d.result_hit:
            by_offset[offset]["hits"] += 1
    
    # Calcular taxa
    for offset in by_offset:
        total = by_offset[offset]["total"]
        hits = by_offset[offset]["hits"]
        by_offset[offset]["rate"] = round(hits / total * 100, 1) if total else 0
    
    return dict(sorted(by_offset.items()))


def simulate_what_if(decisions: List[Decision]) -> Dict[str, Any]:
    """Simula cenários 'e se?' com diferentes estratégias."""
    results = {}
    
    # 1. Baseline: Apostar em TUDO (ignorar Triple Rate)
    all_sda_recommendations = [d for d in decisions if d.sda_should_bet]
    all_hits = [d for d in all_sda_recommendations if d.result_hit is True]
    results["baseline_always_bet"] = {
        "bets": len(all_sda_recommendations),
        "hits": len(all_hits),
        "rate": round(len(all_hits) / len(all_sda_recommendations) * 100, 1) if all_sda_recommendations else 0
    }
    
    # 2. Atual: Com Triple Rate
    current_bets = [d for d in decisions if d.final_action == "APOSTAR"]
    current_hits = [d for d in current_bets if d.result_hit is True]
    results["current_with_tr"] = {
        "bets": len(current_bets),
        "hits": len(current_hits),
        "rate": round(len(current_hits) / len(current_bets) * 100, 1) if current_bets else 0
    }
    
    # 3. Só confiança alta
    high_conf = [d for d in decisions if d.tr_confidence == "alta" and d.sda_should_bet]
    high_hits = [d for d in high_conf if d.result_hit is True]
    results["only_high_confidence"] = {
        "bets": len(high_conf),
        "hits": len(high_hits),
        "rate": round(len(high_hits) / len(high_conf) * 100, 1) if high_conf else 0
    }
    
    return results


def analyze_by_direction(decisions: List[Decision]) -> Dict[str, Any]:
    """Analisa performance separada por direção (CW vs CCW)."""
    # Separar por direção
    cw_decisions = [d for d in decisions if d.spin_direction in ("horario", "cw")]
    ccw_decisions = [d for d in decisions if d.spin_direction in ("anti-horario", "ccw")]
    
    def calc_stats(decs: List[Decision]) -> Dict[str, Any]:
        bets = [d for d in decs if d.final_action == "APOSTAR"]
        hits = [d for d in bets if d.result_hit is True]
        misses = [d for d in bets if d.result_hit is False]
        
        return {
            "total": len(decs),
            "bets": len(bets),
            "hits": len(hits),
            "misses": len(misses),
            "rate": round(len(hits) / len(bets) * 100, 1) if bets else 0
        }
    
    return {
        "cw": calc_stats(cw_decisions),
        "ccw": calc_stats(ccw_decisions)
    }


def print_report(decisions: List[Decision]) -> None:
    """Imprime relatório completo."""
    print("=" * 80)
    print("📊 BACKTEST - DADOS REAIS DO BANCO DE DADOS")
    print("=" * 80)
    print(f"\n📅 Período: {decisions[0].timestamp} até {decisions[-1].timestamp}")
    print(f"📈 Total de decisões analisadas: {len(decisions)}")
    
    # ============================================================
    # NOVO: BACKTEST POR DIREÇÃO
    # ============================================================
    print("\n" + "=" * 80)
    print("🔄 BACKTEST POR DIREÇÃO (CW vs CCW)")
    print("=" * 80)
    
    by_dir = analyze_by_direction(decisions)
    
    cw = by_dir["cw"]
    ccw = by_dir["ccw"]
    
    print(f"\n   {'MÉTRICA':<20} {'CW (HORÁRIO)':>15} {'CCW (ANTI-HORÁRIO)':>20}")
    print("   " + "-" * 55)
    print(f"   {'Total decisões':<20} {cw['total']:>15} {ccw['total']:>20}")
    print(f"   {'Apostas':<20} {cw['bets']:>15} {ccw['bets']:>20}")
    print(f"   {'Acertos':<20} {cw['hits']:>15} {ccw['hits']:>20}")
    print(f"   {'Erros':<20} {cw['misses']:>15} {ccw['misses']:>20}")
    print(f"   {'Taxa de acerto':<20} {cw['rate']:>14.1f}% {ccw['rate']:>19.1f}%")
    
    # Comparativo
    diff = cw['rate'] - ccw['rate']
    if abs(diff) > 5:
        better = "CW" if diff > 0 else "CCW"
        print(f"\n   ⚠️ ATENÇÃO: {better} está {abs(diff):.1f}% melhor que a outra direção!")
    else:
        print(f"\n   ✅ Direções equilibradas (diferença: {abs(diff):.1f}%)")
    
    # ============================================================
    # DETALHES CW
    # ============================================================
    cw_decisions = [d for d in decisions if d.spin_direction in ("horario", "cw")]
    if cw_decisions:
        print("\n" + "-" * 80)
        print("🔵 DETALHES CW (HORÁRIO)")
        print("-" * 80)
        
        perf_cw = analyze_strategy_performance(cw_decisions)
        gale_cw = analyze_gale_performance(cw_decisions)
        
        print(f"   Apostas: {perf_cw['total_bets']} | Acertos: {perf_cw['hits']} | Taxa: {perf_cw['hit_rate']}%")
        print(f"   Puladas: {perf_cw['total_skips']} | Teriam acertado: {perf_cw['skip_analysis']['would_have_hit']}")
        print(f"   Gale: ", end="")
        for level, data in gale_cw.items():
            print(f"{level}={data['hits']}/{data['total']} ", end="")
        print()
    
    # ============================================================
    # DETALHES CCW
    # ============================================================
    ccw_decisions = [d for d in decisions if d.spin_direction in ("anti-horario", "ccw")]
    if ccw_decisions:
        print("\n" + "-" * 80)
        print("🔴 DETALHES CCW (ANTI-HORÁRIO)")
        print("-" * 80)
        
        perf_ccw = analyze_strategy_performance(ccw_decisions)
        gale_ccw = analyze_gale_performance(ccw_decisions)
        
        print(f"   Apostas: {perf_ccw['total_bets']} | Acertos: {perf_ccw['hits']} | Taxa: {perf_ccw['hit_rate']}%")
        print(f"   Puladas: {perf_ccw['total_skips']} | Teriam acertado: {perf_ccw['skip_analysis']['would_have_hit']}")
        print(f"   Gale: ", end="")
        for level, data in gale_ccw.items():
            print(f"{level}={data['hits']}/{data['total']} ", end="")
        print()
    
    # ============================================================
    # PERFORMANCE GERAL (mantido)
    # ============================================================
    print("\n" + "-" * 80)
    print("🎯 PERFORMANCE GERAL SDA-17")
    print("-" * 80)
    
    perf = analyze_strategy_performance(decisions)
    print(f"   Total de apostas:  {perf['total_bets']}")
    print(f"   Acertos:           {perf['hits']}")
    print(f"   Erros:             {perf['misses']}")
    print(f"   Taxa de acerto:    {perf['hit_rate']}%")
    print(f"\n   Puladas:           {perf['total_skips']}")
    print(f"   - Teriam acertado: {perf['skip_analysis']['would_have_hit']} (oportunidade perdida)")
    print(f"   - Teriam errado:   {perf['skip_analysis']['would_have_missed']} (salvo pelo skip)")
    
    # 2. Triple Rate
    print("\n" + "-" * 80)
    print("📈 EFETIVIDADE DO TRIPLE RATE ADVISOR")
    print("-" * 80)
    
    tr = analyze_triple_rate_effectiveness(decisions)
    print(f"   Vezes que vetou aposta: {tr['vetoed_by_tr']}")
    print(f"   - Teria acertado:       {tr['vetoed_would_hit']}")
    print(f"   - Teria errado:         {tr['vetoed_would_miss']}")
    print(f"   Efetividade do veto:    {tr['veto_saved_percent']}% de erros evitados")
    
    print("\n   Por nível de confiança:")
    for conf, data in tr['by_confidence'].items():
        print(f"   - {conf.upper():8} → {data['hits']}/{data['total']} apostas ({data['rate']}%)")
    
    # 3. Gale
    print("\n" + "-" * 80)
    print("💰 PERFORMANCE POR NÍVEL DE GALE")
    print("-" * 80)
    
    gale = analyze_gale_performance(decisions)
    for level, data in gale.items():
        bar = "█" * int(data['rate'] / 5) if data['rate'] > 0 else ""
        print(f"   {level}: {data['hits']:3}/{data['total']:3} ({data['rate']:5.1f}%) {bar}")
    
    # 4. Calibração
    print("\n" + "-" * 80)
    print("🔧 PERFORMANCE POR OFFSET DE CALIBRAÇÃO")
    print("-" * 80)
    
    cal = analyze_calibration(decisions)
    for offset, data in cal.items():
        bar = "█" * int(data['rate'] / 5) if data['rate'] > 0 else ""
        print(f"   Offset {offset:+2}: {data['hits']:3}/{data['total']:3} ({data['rate']:5.1f}%) {bar}")
    
    # 5. Simulação E Se
    print("\n" + "-" * 80)
    print("🔮 SIMULAÇÃO 'E SE?'")
    print("-" * 80)
    
    what_if = simulate_what_if(decisions)
    for scenario, data in what_if.items():
        print(f"   {scenario:25} → {data['hits']}/{data['bets']} ({data['rate']}%)")
    
    print("\n" + "=" * 80)
    print("✅ Backtest concluído!")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Backtest com dados reais do banco")
    parser.add_argument("--session", "-s", help="ID da sessão específica")
    parser.add_argument("--hours", "-H", type=int, default=24, help="Últimas N horas (default: 24)")
    parser.add_argument("--limit", "-l", type=int, default=500, help="Máximo de decisões (default: 500)")
    
    args = parser.parse_args()
    
    print(f"\n🔍 Carregando decisões das últimas {args.hours} horas...")
    
    decisions = load_decisions(
        session_id=args.session,
        hours_back=args.hours,
        limit=args.limit
    )
    
    if not decisions:
        print("❌ Nenhuma decisão encontrada no período especificado.")
        print("   Verifique se o servidor está rodando e salvando decisões.")
        return
    
    print(f"✅ {len(decisions)} decisões carregadas.\n")
    
    print_report(decisions)


if __name__ == "__main__":
    main()
