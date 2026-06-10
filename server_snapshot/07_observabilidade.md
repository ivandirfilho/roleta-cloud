# Observabilidade — Prometheus / Grafana / Alertmanager

## Targets Prometheus
```
prometheus http://localhost:9090/metrics up
roleta-cloud http://roleta-cloud:8766/metrics up
```

## Regras de alerta carregadas
```
RoletaAdaptiveStateLost inactive
RoletaSigmoidEmpty inactive
RoletaStateFileStale inactive
RoletaNoSpinsRecent inactive
RoletaAccuracyDegraded inactive
RoletaMetricsScrapeErrors inactive
RoletaCalibrationFillRateLow inactive
RoletaWheelDistP50High inactive
RoletaDnaRealizeLagHigh firing
RoletaShadowBeatingIncumbent inactive
RoletaKillPullsHigh inactive
RoletaVolatilityExtreme inactive
RoletaBatchTunePullbackBurst inactive
RoletaTargetDown inactive
```

## Alertas ativos agora
```
1 alertas
RoletaDnaRealizeLagHigh firing
```

## Grafana-agent (cloud remoto)
```
active
```
