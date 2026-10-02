"""
PowerTrader AI+ Neural Network Implementation
Real PyTorch-based neural networks for cryptocurrency price prediction
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    from sklearn.preprocessing import MinMaxScaler, StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
    import ta  # Technical Analysis library

    PYTORCH_AVAILABLE = True
except ImportError as e:
    PYTORCH_AVAILABLE = False
    print(f"Warning: PyTorch dependencies not available: {e}")
    print("Run: pip install torch torchvision scikit-learn ta")


class TradingLSTM(nn.Module):
    """
    Advanced LSTM neural network for cryptocurrency price prediction

    Features:
    - Multi-layer LSTM with dropout for regularization
    - Batch normalization for stable training
    - Attention mechanism for focusing on important time steps
    - Multiple output heads for different prediction tasks
    """

    def __init__(
        self,
        input_size: int,
        hidden_size: int = 128,
        num_layers: int = 3,
        output_size: int = 1,
        dropout: float = 0.2,
        use_attention: bool = True,
    ):
        super(TradingLSTM, self).__init__()

        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.use_attention = use_attention

        # LSTM layers with dropout
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=False,
        )

        # Batch normalization
        self.batch_norm = nn.BatchNorm1d(hidden_size)

        # Attention mechanism
        if use_attention:
            self.attention = nn.MultiheadAttention(
                embed_dim=hidden_size, num_heads=8, dropout=dropout, batch_first=True
            )

        # Output layers
        self.dropout = nn.Dropout(dropout)
        self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
        self.fc2 = nn.Linear(hidden_size // 2, output_size)

        # Activation functions
        self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        # LSTM forward pass
        lstm_out, (hidden, cell) = self.lstm(x)

        # Apply attention if enabled
        if self.use_attention:
            attn_out, _ = self.attention(lstm_out, lstm_out, lstm_out)
            # Use the last time step from attention output
            last_output = attn_out[:, -1, :]
        else:
            # Use the last time step from LSTM output
            last_output = lstm_out[:, -1, :]

        # Batch normalization
        last_output = self.batch_norm(last_output)

        # Fully connected layers
        x = self.dropout(last_output)
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        output = self.fc2(x)

        return output


class TradingTransformer(nn.Module):
    """
    Transformer-based architecture for time series prediction
    More advanced than LSTM for capturing long-range dependencies
    """

    def __init__(
        self,
        input_size: int,
        d_model: int = 128,
        nhead: int = 8,
        num_layers: int = 6,
        output_size: int = 1,
        dropout: float = 0.1,
    ):
        super(TradingTransformer, self).__init__()

        self.d_model = d_model
        self.input_projection = nn.Linear(input_size, d_model)

        # Positional encoding
        self.pos_encoding = PositionalEncoding(d_model, dropout)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)

        # Output layers
        self.output_projection = nn.Sequential(
            nn.Linear(d_model, d_model // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(d_model // 2, output_size),
        )

    def forward(self, x):
        # Input projection
        x = self.input_projection(x) * np.sqrt(self.d_model)
        x = self.pos_encoding(x)

        # Transformer encoding
        x = self.transformer(x)

        # Use the last time step for prediction
        x = x[:, -1, :]

        # Output projection
        output = self.output_projection(x)

        return output


class PositionalEncoding(nn.Module):
    """Positional encoding for transformer"""

    def __init__(self, d_model: int, dropout: float = 0.1, max_len: int = 5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer("pe", pe)

    def forward(self, x):
        x = x + self.pe[: x.size(0), :].transpose(0, 1)
        return self.dropout(x)


class FeatureEngineering:
    """
    Advanced feature engineering for cryptocurrency trading
    Creates technical indicators and market microstructure features
    """

    @staticmethod
    def create_technical_features(df: pd.DataFrame) -> pd.DataFrame:
        """Create comprehensive technical analysis features"""

        if len(df) < 50:
            raise ValueError("Need at least 50 data points for technical features")

        # Basic price features
        df["returns"] = df["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df["close"].shift(1))
        df["high_low_ratio"] = df["high"] / df["low"]
        df["open_close_ratio"] = df["open"] / df["close"]

        # Moving averages
        for period in [7, 14, 21, 50]:
            df[f"sma_{period}"] = ta.trend.sma_indicator(df["close"], window=period)
            df[f"ema_{period}"] = ta.trend.ema_indicator(df["close"], window=period)

        # RSI
        for period in [14, 21]:
            df[f"rsi_{period}"] = ta.momentum.rsi(df["close"], window=period)

        # MACD
        df["macd"] = ta.trend.macd_diff(df["close"])
        df["macd_signal"] = ta.trend.macd_signal(df["close"])

        # Bollinger Bands
        bb = ta.volatility.BollingerBands(df["close"])
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (
            df["bb_upper"] - df["bb_lower"]
        )

        # Stochastic
        stoch = ta.momentum.StochasticOscillator(df["high"], df["low"], df["close"])
        df["stoch_k"] = stoch.stoch()
        df["stoch_d"] = stoch.stoch_signal()

        # ADX
        df["adx"] = ta.trend.adx(df["high"], df["low"], df["close"])

        # Williams %R
        df["williams_r"] = ta.momentum.williams_r(df["high"], df["low"], df["close"])

        # Volume features
        if "volume" in df.columns:
            df["volume_sma"] = df["volume"].rolling(window=14).mean()
            df["volume_ratio"] = df["volume"] / df["volume_sma"]
            df["price_volume"] = df["close"] * df["volume"]

        # Volatility features
        df["volatility"] = df["returns"].rolling(window=14).std()
        df["price_range"] = (df["high"] - df["low"]) / df["close"]

        # Momentum features
        for period in [1, 5, 10, 20]:
            df[f"momentum_{period}"] = df["close"] / df["close"].shift(period) - 1

        # Support and resistance levels (simplified)
        df["resistance"] = df["high"].rolling(window=20).max()
        df["support"] = df["low"].rolling(window=20).min()
        df["distance_to_resistance"] = (df["resistance"] - df["close"]) / df["close"]
        df["distance_to_support"] = (df["close"] - df["support"]) / df["close"]

        return df

    @staticmethod
    def create_sequences(
        data: np.ndarray, sequence_length: int, target_column: int = -1
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for time series prediction

        Args:
            data: Input data array
            sequence_length: Length of input sequences
            target_column: Column index for target variable

        Returns:
            Tuple of (X, y) arrays
        """
        X, y = [], []

        for i in range(len(data) - sequence_length):
            # Input sequence
            sequence = data[i : i + sequence_length, :-1]  # All features except target
            # Target value
            target = data[i + sequence_length, target_column]

            X.append(sequence)
            y.append(target)

        return np.array(X), np.array(y)


def _best_model_path() -> str:
    """Checkpoint of the best model so far, in the user models folder."""
    import pt_paths

    return os.path.join(pt_paths.models_dir(), "best_model.pth")


class ModelTrainer:
    """
    Comprehensive model training and evaluation system
    """

    def __init__(self, model_type: str = "lstm", device: str = None):
        self.model_type = model_type.lower()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.scaler = None
        self.feature_columns = None
        self.training_history = []

        print(f"Initializing ModelTrainer with {self.model_type} on {self.device}")

    def prepare_data(
        self,
        df: pd.DataFrame,
        sequence_length: int = 60,
        target_column: str = "close",
        test_size: float = 0.2,
    ) -> Dict:
        """
        Prepare data for training with feature engineering
        """
        print("Preparing data with feature engineering...")

        # Feature engineering
        df_features = FeatureEngineering.create_technical_features(df.copy())

        # Remove rows with NaN values
        df_features = df_features.dropna()

        if len(df_features) < sequence_length + 50:
            raise ValueError(
                f"Not enough data after feature engineering. Need at least {sequence_length + 50} rows"
            )

        # Select features (exclude timestamp and target)
        feature_columns = [
            col
            for col in df_features.columns
            if col not in ["timestamp", "date"] and col != target_column
        ]

        # Add target column at the end
        feature_columns.append(target_column)
        self.feature_columns = feature_columns

        # Prepare data array
        data = df_features[feature_columns].values.astype(np.float32)

        # Scale features
        self.scaler = StandardScaler()
        data_scaled = self.scaler.fit_transform(data)

        # Create sequences
        X, y = FeatureEngineering.create_sequences(
            data_scaled, sequence_length, target_column=-1
        )

        # Train-test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, shuffle=False
        )

        print(
            f"Data prepared: {X_train.shape[0]} training samples, {X_test.shape[0]} test samples"
        )
        print(
            f"Features: {len(feature_columns) - 1}, Sequence length: {sequence_length}"
        )

        return {
            "X_train": X_train,
            "X_test": X_test,
            "y_train": y_train,
            "y_test": y_test,
            "feature_names": feature_columns[:-1],
            "target_name": target_column,
        }

    def create_model(self, input_size: int, **kwargs) -> nn.Module:
        """Create the specified model architecture"""

        if self.model_type == "lstm":
            model = TradingLSTM(
                input_size=input_size,
                hidden_size=kwargs.get("hidden_size", 128),
                num_layers=kwargs.get("num_layers", 3),
                dropout=kwargs.get("dropout", 0.2),
                use_attention=kwargs.get("use_attention", True),
            )
        elif self.model_type == "transformer":
            model = TradingTransformer(
                input_size=input_size,
                d_model=kwargs.get("d_model", 128),
                nhead=kwargs.get("nhead", 8),
                num_layers=kwargs.get("num_layers", 6),
                dropout=kwargs.get("dropout", 0.1),
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")

        return model.to(self.device)

    def train_model(
        self,
        data: Dict,
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        **model_kwargs,
    ) -> Dict:
        """
        Train the neural network model
        """
        print(f"Starting {self.model_type.upper()} training...")

        # Prepare data loaders
        X_train = torch.FloatTensor(data["X_train"]).to(self.device)
        y_train = torch.FloatTensor(data["y_train"]).to(self.device)
        X_test = torch.FloatTensor(data["X_test"]).to(self.device)
        y_test = torch.FloatTensor(data["y_test"]).to(self.device)

        train_dataset = TensorDataset(X_train, y_train)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        # Create model
        input_size = X_train.shape[2]
        self.model = self.create_model(input_size, **model_kwargs)

        # Loss function and optimizer
        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", factor=0.5, patience=10
        )

        # Training loop
        self.training_history = []
        best_loss = float("inf")
        patience_counter = 0
        early_stopping_patience = 15

        for epoch in range(epochs):
            # Training phase
            self.model.train()
            train_loss = 0.0

            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()

                outputs = self.model(batch_X)
                loss = criterion(outputs.squeeze(), batch_y)

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation phase
            self.model.eval()
            with torch.no_grad():
                val_outputs = self.model(X_test)
                val_loss = criterion(val_outputs.squeeze(), y_test).item()

            # Learning rate scheduling
            scheduler.step(val_loss)

            # Early stopping
            if val_loss < best_loss:
                best_loss = val_loss
                patience_counter = 0
                # Save best model (user models folder, see pt_paths)
                torch.save(self.model.state_dict(), _best_model_path())
            else:
                patience_counter += 1

            # Record training history
            self.training_history.append(
                {
                    "epoch": epoch + 1,
                    "train_loss": train_loss,
                    "val_loss": val_loss,
                    "lr": optimizer.param_groups[0]["lr"],
                }
            )

            # Print progress
            if (epoch + 1) % 10 == 0 or epoch == 0:
                print(
                    f"Epoch {epoch + 1}/{epochs} - "
                    f"Train Loss: {train_loss:.6f} - "
                    f"Val Loss: {val_loss:.6f} - "
                    f"LR: {optimizer.param_groups[0]['lr']:.6f}"
                )

            # Early stopping
            if patience_counter >= early_stopping_patience:
                print(f"Early stopping triggered at epoch {epoch + 1}")
                break

        # Load best model
        self.model.load_state_dict(torch.load(_best_model_path()))

        # Evaluate model
        evaluation_results = self.evaluate_model(data)

        print(f"Training completed!")
        print(f"Best validation loss: {best_loss:.6f}")

        return {
            "training_history": self.training_history,
            "best_loss": best_loss,
            "evaluation": evaluation_results,
        }

    def evaluate_model(self, data: Dict) -> Dict:
        """
        Evaluate the trained model
        """
        if self.model is None:
            raise ValueError("Model not trained yet")

        self.model.eval()

        X_test = torch.FloatTensor(data["X_test"]).to(self.device)
        y_test = data["y_test"]

        with torch.no_grad():
            predictions = self.model(X_test).cpu().numpy().squeeze()

        # Calculate metrics
        mse = mean_squared_error(y_test, predictions)
        mae = mean_absolute_error(y_test, predictions)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test, predictions)

        # Calculate directional accuracy
        y_test_direction = np.diff(y_test) > 0
        pred_direction = np.diff(predictions) > 0
        directional_accuracy = np.mean(y_test_direction == pred_direction)

        results = {
            "mse": float(mse),
            "mae": float(mae),
            "rmse": float(rmse),
            "r2_score": float(r2),
            "directional_accuracy": float(directional_accuracy),
        }

        print("Model Evaluation Results:")
        print(f"  MSE: {mse:.6f}")
        print(f"  MAE: {mae:.6f}")
        print(f"  RMSE: {rmse:.6f}")
        print(f"  R² Score: {r2:.4f}")
        print(f"  Directional Accuracy: {directional_accuracy:.4f}")

        return results

    def save_model(self, filepath: str, metadata: Dict = None):
        """Save the trained model with metadata"""
        if self.model is None:
            raise ValueError("No model to save")

        save_dict = {
            "model_state_dict": self.model.state_dict(),
            "model_type": self.model_type,
            "scaler": self.scaler,
            "feature_columns": self.feature_columns,
            "training_history": self.training_history,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        }

        torch.save(save_dict, filepath)
        print(f"Model saved to: {filepath}")

    def load_model(self, filepath: str):
        """Load a previously trained model"""
        checkpoint = torch.load(filepath, map_location=self.device)

        self.model_type = checkpoint["model_type"]
        self.scaler = checkpoint["scaler"]
        self.feature_columns = checkpoint["feature_columns"]
        self.training_history = checkpoint.get("training_history", [])

        # Recreate model architecture
        if self.feature_columns:
            input_size = len(self.feature_columns) - 1  # Exclude target
            self.model = self.create_model(input_size)
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.eval()

        print(f"Model loaded from: {filepath}")
        return checkpoint.get("metadata", {})


def check_pytorch_installation():
    """Check if PyTorch and dependencies are properly installed"""
    missing_deps = []

    try:
        import torch

        print(f"✓ PyTorch {torch.__version__} installed")
        print(f"✓ CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"✓ CUDA device: {torch.cuda.get_device_name()}")
    except ImportError:
        missing_deps.append("torch")

    try:
        import sklearn

        print(f"✓ scikit-learn {sklearn.__version__} installed")
    except ImportError:
        missing_deps.append("scikit-learn")

    try:
        import ta

        print("✓ Technical Analysis library installed")
    except ImportError:
        missing_deps.append("ta")

    if missing_deps:
        print(f"\n❌ Missing dependencies: {', '.join(missing_deps)}")
        print("Run: pip install " + " ".join(missing_deps))
        return False

    print("\n✅ All dependencies installed successfully!")
    return True


if __name__ == "__main__":
    # Example usage and testing
    check_pytorch_installation()
