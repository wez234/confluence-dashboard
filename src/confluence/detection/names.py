"""Detector identifiers and display names (dependency-free, used by the dashboard)."""
BASE_DETECTORS = ["zscore", "moving_average", "isolation_forest", "one_class_svm", "lstm_autoencoder"]
ALL_DETECTORS = BASE_DETECTORS + ["ensemble"]
DISPLAY = {"zscore": "Z-score", "moving_average": "Moving average", "isolation_forest": "Isolation Forest",
           "one_class_svm": "One-Class SVM", "lstm_autoencoder": "LSTM autoencoder", "ensemble": "Ensemble"}
FAMILY = {"zscore": "Statistical", "moving_average": "Statistical", "isolation_forest": "Machine learning",
          "one_class_svm": "Machine learning", "lstm_autoencoder": "Deep learning", "ensemble": "Ensemble"}
