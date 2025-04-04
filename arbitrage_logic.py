import networkx as nx
import requests
import json
import streamlit as st # Import for caching and potential logging/warnings
from typing import List, Dict, Any, Tuple, Optional, Set

# --- Configuration and Constants ---
CURRENCY_CONFIG_FILE = 'currencies.json'
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"

# --- Logic Functions ---

@st.cache_data
def load_currencies(config_file: str = CURRENCY_CONFIG_FILE) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """Loads currency definitions and creates a ticker-to-ID map."""
    try:
        with open(config_file, 'r') as f:
            currencies = json.load(f)
        ticker_to_id_map = {item['ticker'].lower(): item['id'] for item in currencies}
        return currencies, ticker_to_id_map
    except FileNotFoundError:
        st.error(f"Error: Currency configuration file '{config_file}' not found.")
        return [], {}
    except json.JSONDecodeError:
        st.error(f"Error: Could not decode JSON from '{config_file}'.")
        return [], {}

def get_details_from_tickers(
    input_tickers: List[str],
    ticker_to_id_map: Dict[str, str]
) -> Tuple[List[str], List[str], Dict[str, str], Dict[str, str], List[str]]:
    """
    Processes user input tickers, finds corresponding IDs, and returns mappings.
    Also returns a list of tickers that were not found.
    """
    selected_ids_set: Set[str] = set()
    selected_tickers_clean_set: Set[str] = set()
    name_ticker_map: Dict[str, str] = {} # api_id -> ticker
    id_ticker_map: Dict[str, str] = {}   # ticker -> api_id
    not_found_tickers: List[str] = []

    for ticker in input_tickers:
        ticker_lower = ticker.strip().lower()
        if not ticker_lower:
            continue

        api_id = ticker_to_id_map.get(ticker_lower)
        if api_id:
            selected_ids_set.add(api_id)
            selected_tickers_clean_set.add(ticker_lower)
            name_ticker_map[api_id] = ticker_lower
            id_ticker_map[ticker_lower] = api_id
        else:
            not_found_tickers.append(ticker)

    selected_ids = list(selected_ids_set)
    selected_tickers_clean = list(selected_tickers_clean_set)

    return selected_ids, selected_tickers_clean, name_ticker_map, id_ticker_map, not_found_tickers

# Cache API results for a short duration to avoid hitting rate limits during quick checks
@st.cache_data(ttl=60)
def fetch_exchange_rates(_currency_ids: Tuple[str], _vs_tickers: Tuple[str]) -> Optional[Dict[str, Any]]:
    """Fetches exchange rates from CoinGecko API. Uses tuples for cache keys."""
    if not _currency_ids or not _vs_tickers:
        st.warning("Cannot fetch rates: Missing currency IDs or target tickers.")
        return None

    # Convert tuples back to lists/strings for API call
    currency_ids_list = list(_currency_ids)
    vs_tickers_list = list(_vs_tickers)

    params = {
        'ids': ','.join(currency_ids_list),
        'vs_currencies': ','.join(vs_tickers_list)
    }
    try:
        # st.info(f"Querying CoinGecko: ids={params['ids']}, vs_currencies={params['vs_currencies']}") # Debug
        response = requests.get(COINGECKO_API_URL, params=params)
        response.raise_for_status()
        data = response.json()
        # Filter out empty responses which CoinGecko sometimes returns for unsupported pairs
        return {k: v for k, v in data.items() if v}

    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data from CoinGecko API: {e}")
        return None
    except json.JSONDecodeError:
        st.error("Error: Could not decode JSON response from CoinGecko API.")
        return None

def build_graph(data: Dict[str, Any], name_ticker_map: Dict[str, str]) -> nx.DiGraph:
    """Builds the weighted directed graph from API data."""
    g = nx.DiGraph()
    edges_to_add = []
    all_selected_tickers = set(name_ticker_map.values()) # Tickers we intend to include

    # Ensure all target tickers are added as nodes initially
    for ticker in all_selected_tickers:
        g.add_node(ticker)

    for api_id_from, rates in data.items():
        ticker_from = name_ticker_map.get(api_id_from)
        if not ticker_from or ticker_from not in all_selected_tickers:
            continue # Skip if the source currency isn't selected/mapped

        for ticker_to, rate in rates.items():
            # Ensure the target ticker is one of the selected ones AND has a valid rate
            if ticker_to in all_selected_tickers and rate is not None and isinstance(rate, (int, float)) and rate > 0:
                edges_to_add.append((ticker_from, ticker_to, float(rate))) # Ensure rate is float

    g.add_weighted_edges_from(edges_to_add)

    # Remove nodes that ended up with no connections (API might lack data)
    isolated_nodes = list(nx.isolates(g))
    if isolated_nodes:
        # st.warning(f"Removing isolated nodes (no exchange data found): {', '.join(isolated_nodes)}")
        g.remove_nodes_from(isolated_nodes)

    return g

def calculate_path_weight(graph: nx.DiGraph, path: List[str]) -> float:
    """Calculates the product of edge weights along a path."""
    weight = 1.0
    if len(path) < 2:
        return 0.0 # Path needs at least 2 nodes for an edge

    try:
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i+1]
            if graph.has_edge(u, v):
                 edge_weight = graph[u][v]['weight']
                 weight *= edge_weight
            else:
                 st.warning(f"Edge missing in path calculation: {u} -> {v}")
                 return 0.0 # Invalid path
        return weight
    except KeyError as e:
        # This might indicate an issue with how edges were added or accessed
        st.error(f"Internal Error: Could not access edge weight for {e}. Path: {path}")
        return 0.0


def analyze_all_pairs(graph: nx.DiGraph, progress_callback=None) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Analyzes all pairs of nodes for arbitrage opportunities."""
    min_factor = float('inf')
    max_factor = float('-inf') # Use negative infinity for max comparison
    min_details = None
    max_details = None

    nodes = list(graph.nodes)
    if len(nodes) < 2:
        st.warning("Need at least two currencies with exchange data to find paths.")
        return None, None

    total_pairs = len(nodes) * (len(nodes) - 1)
    processed_pairs = 0
    path_cutoff = 5 # Limit path length to avoid excessive computation

    for i in range(len(nodes)):
        for j in range(len(nodes)):
            if i == j:
                continue

            node1 = nodes[i]
            node2 = nodes[j]

            try:
                # Find paths (convert generator to list)
                forward_paths = list(nx.all_simple_paths(graph, source=node1, target=node2, cutoff=path_cutoff))
                reverse_paths = list(nx.all_simple_paths(graph, source=node2, target=node1, cutoff=path_cutoff))

            except nx.NodeNotFound:
                # Should not happen if graph is built correctly, but handle defensively
                processed_pairs += 1
                if progress_callback and total_pairs > 0: progress_callback(min(1.0, processed_pairs / total_pairs))
                continue
            except nx.NetworkXNoPath:
                 # Handle cases where no path exists cleanly
                 processed_pairs += 1
                 if progress_callback and total_pairs > 0: progress_callback(min(1.0, processed_pairs / total_pairs))
                 continue


            if not forward_paths or not reverse_paths:
                processed_pairs += 1
                if progress_callback and total_pairs > 0: progress_callback(min(1.0, processed_pairs / total_pairs))
                continue # Need both forward and reverse paths

            for f_path in forward_paths:
                for r_path in reverse_paths:
                    if not f_path or len(f_path) < 2 or not r_path or len(r_path) < 2:
                        continue # Skip invalid or single-node paths

                    forward_weight = calculate_path_weight(graph, f_path)
                    reverse_weight = calculate_path_weight(graph, r_path)

                    if forward_weight <= 0 or reverse_weight <= 0:
                        continue # Ignore paths with zero or negative weights

                    factor = forward_weight * reverse_weight

                    # Update min factor (any factor is potentially interesting)
                    if factor < min_factor:
                        min_factor = factor
                        min_details = {
                            'from': node1, 'to': node2,
                            'f_path': f_path, 'f_weight': forward_weight,
                            'r_path': r_path, 'r_weight': reverse_weight,
                            'factor': factor
                        }

                    # Update max factor only if it represents arbitrage (factor > 1)
                    # Use a small tolerance to avoid floating point noise around 1.0
                    if factor > 1.00001 and factor > max_factor:
                        max_factor = factor
                        max_details = {
                            'from': node1, 'to': node2,
                            'f_path': f_path, 'f_weight': forward_weight,
                            'r_path': r_path, 'r_weight': reverse_weight,
                            'factor': factor
                        }

            # Update progress after processing all path combinations for this pair
            processed_pairs += 1
            if progress_callback and total_pairs > 0: progress_callback(min(1.0, processed_pairs / total_pairs))

    return min_details, max_details