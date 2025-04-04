import streamlit as st
import arbitrage_logic as logic # Import the separated logic
import re
import pandas as pd # For timestamp

# --- Helper Functions specific to UI ---

def parse_tickers_from_text(text_input: str) -> list[str]:
    """Extracts unique, non-empty tickers from comma/space/newline separated text."""
    # Replace commas and newlines with spaces, then split
    tickers = re.split(r'[ ,\n]+', text_input)
    # Filter out empty strings, convert to lowercase, and get unique
    # Return as a list, preserving order might not be critical here
    return sorted(list(set(t.strip().lower() for t in tickers if t.strip())))


# --- Streamlit App ---

st.set_page_config(page_title="Crypto Arbitrage Finder", layout="wide")

# --- Sidebar ---
with st.sidebar:
    st.header("Settings")
    st.markdown("""
    This tool analyzes cryptocurrency exchange rates to find potential arbitrage opportunities,
    highlighting market inefficiencies based on CoinGecko data.
    """)

    # Load available currencies for mapping and multiselect options
    all_currencies, ticker_to_id_map = logic.load_currencies()
    if not all_currencies:
        st.error("Failed to load currency definitions. Cannot proceed.")
        st.stop()

    # Prepare options for multiselect
    available_tickers_options = sorted([c['ticker'] for c in all_currencies])

    st.subheader("Select Currencies")
    st.markdown("Select default currencies or add your own below.")

    # Multiselect for predefined currencies
    default_selection = available_tickers_options[:7] # Default to first 7
    selected_defaults = st.multiselect(
        "Select from available currencies:",
        options=available_tickers_options,
        default=default_selection
    )

    # Text input for adding more currencies
    additional_tickers_input = st.text_input(
        "Add additional tickers (comma/space separated):",
        placeholder="e.g., doge, dot, avax"
    )

    st.subheader("Investment Analysis")
    initial_investment = st.number_input(
        "Initial Investment Amount (in starting currency):",
        min_value=0.01,
        value=1000.0,
        step=100.0,
        format="%.2f"
    )

    # Add attribution
    st.markdown("---")
    st.markdown("Developed based on [Advanced Python for Analytics](https://www.coursicle.com/usu/courses/DATA/5500/) homework requirements of [Andrew Brim](https://www.linkedin.com/in/andrew-brim-phd-msfe-7043ba4/).")
    st.markdown(f"Using data from [CoinGecko](https://www.coingecko.com/en/api). Prices cached for 60s.")
    # Get current time using pandas for reliable timezone handling
    try:
        current_time = pd.Timestamp.now(tz='America/Denver').strftime('%Y-%m-%d %H:%M:%S %Z')
    except Exception: # Fallback if pandas fails for any reason
        current_time = "Time unavailable"
    st.markdown(f"Current Location: Logan, Utah, United States. Current Time: {current_time}")


# --- Main Area ---
st.title("💰 Crypto Arbitrage Finder")
st.markdown("Find potential arbitrage by analyzing multi-step conversion paths between cryptocurrencies.")

if st.button("Find Arbitrage Opportunities", key="find_button"):

    # 1. Combine Tickers from Multiselect and Text Input
    additional_tickers = parse_tickers_from_text(additional_tickers_input)
    # Combine, ensure lowercase, remove duplicates, and sort
    combined_tickers_raw = sorted(list(set(
        [t.lower() for t in selected_defaults] + additional_tickers
    )))

    if len(combined_tickers_raw) < 2:
        st.warning("Please select or add at least two valid ticker symbols in total.")
        st.stop()

    # 2. Get Currency Details (IDs, Maps) using the logic module
    selected_ids, selected_tickers_clean, name_ticker_map, id_ticker_map, not_found = logic.get_details_from_tickers(
        combined_tickers_raw, ticker_to_id_map
    )

    # Report any tickers entered manually that weren't found in our config
    manually_added_not_found = [t for t in additional_tickers if t in not_found]
    if manually_added_not_found:
        st.warning(f"Manually added tickers not found in config and skipped: `{', '.join(manually_added_not_found)}`")
    # Also report if a default selection somehow failed mapping (less likely)
    default_not_found = [t for t in selected_defaults if t.lower() in not_found]
    if default_not_found:
         st.warning(f"Selected default tickers not found during mapping (check config?): `{', '.join(default_not_found)}`")


    if len(selected_tickers_clean) < 2:
        st.error("Fewer than two valid and known tickers selected after processing. Cannot perform analysis.")
        st.stop()

    st.info(f"Analyzing: `{', '.join(selected_tickers_clean)}`")

    # 3. Fetch Data (include 'usd' for profit calculation)
    vs_list = sorted(list(set(selected_tickers_clean + ['usd'])))
    # Convert lists to tuples for caching in fetch_exchange_rates
    selected_ids_tuple = tuple(sorted(selected_ids))
    vs_list_tuple = tuple(vs_list)

    with st.spinner("Fetching live exchange rates (incl. USD) from CoinGecko..."):
        exchange_data = logic.fetch_exchange_rates(selected_ids_tuple, vs_list_tuple)

    if not exchange_data:
        st.error("Failed to fetch exchange data. CoinGecko might be unavailable or the selected pairs are not supported.")
        st.stop()

    # Extract USD rates for later calculation
    usd_rates = {}
    for api_id, rates in exchange_data.items():
         ticker = name_ticker_map.get(api_id)
         if ticker and 'usd' in rates and isinstance(rates['usd'], (int, float)): # Check type
                usd_rates[ticker] = float(rates['usd'])

    if not usd_rates and len(selected_tickers_clean)>0 : # only warn if we expected some currencies
         st.warning("Could not fetch USD exchange rates for the selected currencies. Profit calculation in USD will be unavailable.")


    # 4. Build Graph
    with st.spinner("Building currency exchange graph..."):
        graph = logic.build_graph(exchange_data, name_ticker_map)

    if graph.number_of_nodes() < 2 or graph.number_of_edges() == 0:
         st.warning("Could not build a connected graph. Insufficient exchange data found between the selected currencies.")
         # Optionally show which nodes were isolated:
         nodes_in_graph = set(graph.nodes())
         missing_nodes = set(selected_tickers_clean) - nodes_in_graph
         if missing_nodes:
             st.info(f"Tickers selected but not included in graph (likely no data): `{', '.join(missing_nodes)}`")
         st.stop()


    # 5. Analyze Paths
    st.info("Analyzing trading paths... (this may take a few moments)")
    progress_bar = st.progress(0)
    def update_progress(value):
        progress_bar.progress(min(value, 1.0)) # Ensure progress doesn't exceed 1.0

    min_details, max_details = logic.analyze_all_pairs(graph, progress_callback=update_progress)
    progress_bar.empty() # Remove progress bar

    st.success("Analysis Complete!")

    # 6. Display Results
    col1, col2 = st.columns(2)

    # --- Loss Potential Column ---
    with col1:
        st.subheader("📉 Largest Loss Potential")
        if min_details and min_details['factor'] < 0.99999 : # Use tolerance
             factor = min_details['factor']
             start_currency = min_details['from']

             st.metric(label=f"Lowest Factor ({start_currency} → ... → {start_currency})", value=f"{factor:.6f}")
             st.write(f"**Route:** `{min_details['from']}` → `{min_details['to']}` → ... → `{min_details['r_path'][-1]}` (Implied return)")
             st.write(f"**Forward Path:** `{' → '.join(min_details['f_path'])}` (Rate: {min_details['f_weight']:.6f})")
             st.write(f"**Reverse Path:** `{' → '.join(min_details['r_path'])}` (Rate: {min_details['r_weight']:.6f})")

             st.markdown("---")
             st.markdown("**Investment Impact**")
             loss_units = initial_investment * (1.0 - factor) # Positive value representing loss
             st.write(f"Starting with `{initial_investment:,.2f} {start_currency.upper()}`...")
             st.write(f"...potential loss indicated by this inefficiency: **`{loss_units:,.6f} {start_currency.upper()}`**")

             # Calculate loss in USD if possible
             start_price_usd = usd_rates.get(start_currency)
             if start_price_usd and start_price_usd > 0:
                 loss_usd = loss_units * start_price_usd
                 st.write(f"...Approximate value of loss: **`$ {loss_usd:,.2f} USD`** (at 1 {start_currency.upper()} ≈ ${start_price_usd:,.2f} USD)")
             else:
                 st.caption("(USD rate for starting currency not available/valid for value calculation)")

        elif min_details:
             st.info(f"The lowest factor found ({min_details['factor']:.6f}) was not significantly less than 1.0.")
        else:
             st.info("No cycles resulting in a factor significantly less than 1.0 were found.")

    # --- Arbitrage Opportunity Column ---
    with col2:
        st.subheader("📈 Best Arbitrage Opportunity")
        if max_details and max_details['factor'] > 1.00001: # Use tolerance
            factor = max_details['factor']
            start_currency = max_details['from']

            st.metric(label=f"Highest Factor ({start_currency} → ... → {start_currency})", value=f"{factor:.6f}", delta=f"{((factor-1)*100):.2f}% gain")
            st.write(f"**Route:** `{max_details['from']}` → `{max_details['to']}` → ... → `{max_details['r_path'][-1]}` (Implied return)")
            st.write(f"**Forward Path:** `{' → '.join(max_details['f_path'])}` (Rate: {max_details['f_weight']:.6f})")
            st.write(f"**Reverse Path:** `{' → '.join(max_details['r_path'])}` (Rate: {max_details['r_weight']:.6f})")

            st.markdown("---")
            st.markdown("**Investment Impact**")
            profit_units = initial_investment * (factor - 1.0)
            st.write(f"Starting with `{initial_investment:,.2f} {start_currency.upper()}`...")
            st.write(f"...potential profit indicated by this inefficiency: **`{profit_units:,.6f} {start_currency.upper()}`**")

            # Calculate profit in USD if possible
            start_price_usd = usd_rates.get(start_currency)
            if start_price_usd and start_price_usd > 0:
                profit_usd = profit_units * start_price_usd
                st.write(f"...Approximate value of profit: **`$ {profit_usd:,.2f} USD`** (at 1 {start_currency.upper()} ≈ ${start_price_usd:,.2f} USD)")
                st.success("Potential gain identified!")
            else:
                st.caption("(USD rate for starting currency not available/valid for value calculation)")

        else:
            st.info("No significant arbitrage opportunities (factor > 1.00001) found.")

else:
    # Initial instruction when the app loads
    st.info("Select currencies or add your own in the sidebar, adjust investment, and click the button.")