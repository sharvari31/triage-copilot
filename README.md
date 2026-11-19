# 🤖 ML Model Comparison Engine

> Upload any dataset. Select a target. Click Run. Get a full ML model comparison with explainability and a plain-English recommendation — automatically.

**Live Demo:** [Coming soon on Streamlit Cloud]  
**Built by:** Sharvari Gajendragadkar

---

## What It Does

Most ML projects train one model. This trains **all of them** — simultaneously — and tells you which one wins and *why*.

Upload a CSV → Select target column → Click Run Analysis → Get:

- 📊 **Model comparison table** — Accuracy, F1, Precision, Recall, AUC (or RMSE, MAE, R² for regression)
- 🏆 **Automatic best model recommendation** with plain English reasoning
- 🔍 **SHAP explainability** — which features actually matter and why
- 📈 **Interactive Plotly charts** — confusion matrices, feature importance, learning curves
- ⚡ **Cross-validation** — no lucky splits, real generalization scores

---

## Models Compared

### Classification
| Model | Library |
|-------|---------|
| Logistic Regression | scikit-learn |
| Decision Tree | scikit-learn |
| Random Forest | scikit-learn |
| Gradient Boosting | scikit-learn |
| XGBoost | xgboost |
| Support Vector Machine | scikit-learn |
| K-Nearest Neighbors | scikit-learn |
| Naive Bayes | scikit-learn |
| Extra Trees | scikit-learn |
| AdaBoost | scikit-learn |

### Regression
| Model | Library |
|-------|---------|
| Linear Regression | scikit-learn |
| Ridge Regression | scikit-learn |
| Lasso Regression | scikit-learn |
| Decision Tree Regressor | scikit-learn |
| Random Forest Regressor | scikit-learn |
| Gradient Boosting Regressor | scikit-learn |
| XGBoost Regressor | xgboost |
| SVR | scikit-learn |
| KNN Regressor | scikit-learn |
| Extra Trees Regressor | scikit-learn |

---

## Tech Stack

```
Python 3.10+
Pandas + NumPy        → Data handling and preprocessing
Scikit-learn          → 9 out of 10 models per problem type
XGBoost               → Gradient boosted trees
SHAP                  → Model explainability
Plotly                → Interactive visualizations
Streamlit             → Web interface
```

---

## Run Locally

```bash
git clone https://github.com/sharvari31/ml-model-comparison
cd ml-model-comparison
pip install -r requirements.txt
streamlit run app.py
```

---

## How It Works

### 1. Upload & Detect
Drop any CSV. The engine auto-detects column types, missing values, and cardinality. You pick the target column.

### 2. Auto Preprocessing
- Missing values → median/mode imputation
- Categorical columns → one-hot encoding
- Numerical features → standard scaling
- High-cardinality columns → label encoding

### 3. Problem Type Detection
Selects classification vs regression automatically based on the target column's unique value count and dtype. You can override manually.

### 4. Train All Models
Every model trains with the same preprocessed data and same train/test split (80/20 + stratified for classification).

### 5. Cross-Validation
5-fold cross-validation on every model. Reports mean ± std. No cherry-picked results.

### 6. SHAP Explainability
For the best model:
- **Summary plot** — overall feature importance
- **Bar plot** — mean |SHAP| values per feature
- **Waterfall plot** — single prediction breakdown

### 7. Plain English Recommendation
```
✅ Best Model: Random Forest
Why: Highest CV F1 score (0.924 ± 0.018) with low variance, suggesting 
stable generalization. XGBoost scored marginally lower (0.911) but took 
3x longer to train. For this dataset size (2,847 rows), Random Forest 
offers the best accuracy-to-speed tradeoff.
```

---

## Sample Datasets to Try

| Dataset | Type | Source |
|---------|------|--------|
| Titanic | Classification | [Kaggle](https://www.kaggle.com/c/titanic) |
| Heart Disease | Classification | [UCI ML Repo](https://archive.ics.uci.edu/ml/datasets/heart+disease) |
| House Prices | Regression | [Kaggle](https://www.kaggle.com/c/house-prices-advanced-regression-techniques) |
| Iris | Classification | Built into sklearn |
| Diabetes | Regression | Built into sklearn |

---

## Project Structure

```
ml-model-comparison/
├── app.py                  # Streamlit interface
├── models/
│   ├── trainer.py          # Train all models with cross-validation
│   ├── evaluator.py        # Metrics computation
│   └── explainer.py        # SHAP integration
├── utils/
│   ├── preprocessor.py     # Auto feature engineering pipeline
│   └── recommender.py      # Best model selection + reasoning
└── requirements.txt
```

---

## What I Learned Building This

- Every major classification and regression algorithm — when each excels and why
- Cross-validation strategy — why single train/test splits lie
- Evaluation metric selection — accuracy vs F1 vs AUC and when each matters
- SHAP values — the math behind model explainability
- Automated preprocessing pipelines — handling real-world messy data
- Streamlit session state — managing complex multi-step app flows

---

## Connect

**LinkedIn:** [linkedin.com/in/sharvari-gajendragadkar](https://linkedin.com/in/sharvari-gajendragadkar)  
**GitHub:** [github.com/sharvari31](https://github.com/sharvari31)
