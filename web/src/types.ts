export interface Metrics {
  [k: string]: number;
}

export interface Summary {
  symbol: string;
  kind: string;
  model: string;
  last_date: string;
  last_prob: number;
  signal: string;
  config: any;
  metrics: {
    classification: Metrics;
    strategy: Metrics;
    benchmark: Metrics;
  };
  feature_importance: Record<string, number>;
  n_features: number;
}

export interface Series {
  dates: string[];
  close: (number | null)[];
  proba: (number | null)[];
  position: (number | null)[];
  strategy_nav: (number | null)[];
  benchmark_nav: (number | null)[];
}

export interface RunResult {
  summary: Summary;
  series: Series;
}

export interface Health {
  status: string;
  deepseek_configured: boolean;
  config: string;
}
