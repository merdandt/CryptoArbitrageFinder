# Crypto Arbitrage Finder

## Description

This Streamlit application identifies potential arbitrage opportunities within cryptocurrency markets by analyzing exchange rates fetched in real-time from the CoinGecko API. Arbitrage opportunities arise from temporary price discrepancies across different trading paths. This tool models these paths as a graph and calculates the potential profitability (or loss) of specific multi-step conversion sequences, highlighting market inefficiencies.

It answers the question: "If I start with currency A, convert it through a sequence of other currencies (e.g., A -> B -> C), and then theoretically convert back (using the inverse rates implied by a C -> B -> A path), would I end up with more or less of currency A than I started with?" A factor significantly different from 1.0 indicates a potential opportunity or inefficiency.

## How to Use

1.  **Select Currencies:**
    * Use the **multiselect box** in the sidebar to choose from a list of commonly known cryptocurrencies.
    * Optionally, use the **text input box** below the multiselect to add any other ticker symbols (comma or space-separated) that you want to include in the analysis, even if they weren't in the default list.
    * The analysis will run on the unique combination of currencies from both inputs. The tool needs at least two valid tickers in total.
2.  **Set Investment Amount:** Optionally, adjust the initial investment amount. This is used to calculate the potential profit/loss in both the starting currency units and approximate USD value for the identified opportunities.
3.  **Analyze:** Click the "Find Arbitrage Opportunities" button.
4.  **Review Results:** The application will display:
    * **Largest Loss Potential:** The trading path combination showing the biggest potential decrease in value (factor < 1.0).
    * **Best Arbitrage Opportunity:** The trading path combination showing the highest potential gain (factor > 1.0).
    * **Investment Impact:** For both scenarios, it shows the potential gain/loss based on your initial investment amount, both in units of the starting currency and its approximate USD value (if USD rates are available).

## Features

* Fetches live exchange rates from CoinGecko (including USD rates for value calculation).
* Allows users to select currencies via multiselect and add custom tickers via text input.
* Calculates potential profit/loss based on a user-defined investment amount.
* Uses the NetworkX library to model exchange rates and find paths.
* Separates core logic (`arbitrage_logic.py`) from the UI (`app.py`).
* Identifies best arbitrage (highest factor > 1.0) and largest loss potential (lowest factor < 1.0).

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-directory>
    ```
2.  **Create a virtual environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```
3.  **Install requirements:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the App

Launch the Streamlit application by running:

```bash
streamlit run app.py