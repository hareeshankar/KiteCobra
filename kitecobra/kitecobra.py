"""
KiteCobra - Main Application Entry Point

This module defines the main Reflex application with all pages and routes.
"""

import reflex as rx
from .state import GlobalState


# ============================================================================
# Component Imports (will be created separately)
# ============================================================================

def navbar() -> rx.Component:
    """Navigation bar component."""
    return rx.box(
        rx.hstack(
            rx.hstack(
                rx.icon("activity", size=28, color="cyan"),
                rx.heading("KiteCobra", size="6", color="white"),
                spacing="2",
                align="center",
            ),
            rx.spacer(),
            rx.hstack(
                rx.cond(
                    GlobalState.is_authenticated,
                    rx.hstack(
                        rx.badge(
                            rx.icon("circle", size=8),
                            GlobalState.ticker_status,
                            color_scheme=rx.cond(
                                GlobalState.is_ticker_connected,
                                "green",
                                "red"
                            ),
                        ),
                        rx.text(GlobalState.user_name, color="gray"),
                        rx.button(
                            "Logout",
                            on_click=GlobalState.logout,
                            color_scheme="red",
                            variant="ghost",
                            size="1",
                        ),
                        spacing="4",
                        align="center",
                    ),
                    rx.link(
                        rx.button("Login", color_scheme="cyan"),
                        href="/login",
                    ),
                ),
                spacing="4",
                align="center",
            ),
            width="100%",
            padding="4",
        ),
        background="rgba(0, 0, 0, 0.8)",
        backdrop_filter="blur(10px)",
        position="sticky",
        top="0",
        z_index="100",
        border_bottom="1px solid rgba(255, 255, 255, 0.1)",
    )


def market_stats() -> rx.Component:
    """Market statistics cards showing spot prices."""
    return rx.hstack(
        rx.card(
            rx.vstack(
                rx.text("NIFTY 50", size="1", color="gray"),
                rx.heading(GlobalState.formatted_nifty_spot, size="5", color="white"),
                spacing="1",
                align="start",
            ),
            style={"background": "rgba(0, 200, 200, 0.1)", "border": "1px solid rgba(0, 200, 200, 0.3)"},
        ),
        rx.card(
            rx.vstack(
                rx.text("BANK NIFTY", size="1", color="gray"),
                rx.heading(GlobalState.formatted_banknifty_spot, size="5", color="white"),
                spacing="1",
                align="start",
            ),
            style={"background": "rgba(0, 200, 200, 0.1)", "border": "1px solid rgba(0, 200, 200, 0.3)"},
        ),
        rx.card(
            rx.vstack(
                rx.text("Total P&L", size="1", color="gray"),
                rx.heading(
                    GlobalState.formatted_total_pnl,
                    size="5",
                    color=GlobalState.pnl_color,
                ),
                spacing="1",
                align="start",
            ),
            style={"background": "rgba(0, 200, 200, 0.1)", "border": "1px solid rgba(0, 200, 200, 0.3)"},
        ),
        rx.card(
            rx.vstack(
                rx.text("Available Margin", size="1", color="gray"),
                rx.heading(GlobalState.formatted_margin, size="5", color="white"),
                spacing="1",
                align="start",
            ),
            style={"background": "rgba(0, 200, 200, 0.1)", "border": "1px solid rgba(0, 200, 200, 0.3)"},
        ),
        spacing="4",
        width="100%",
        flex_wrap="wrap",
    )


def trade_row(trade: dict) -> rx.Component:
    """Single trade row in the table."""
    return rx.table.row(
        rx.table.cell(trade["tradingsymbol"]),
        rx.table.cell(
            rx.badge(
                trade["option_type"],
                color_scheme=rx.cond(
                    trade["option_type"] == "CE",
                    "green",
                    "red"
                ),
            )
        ),
        rx.table.cell(
            rx.badge(
                trade["position_type"],
                color_scheme=rx.cond(
                    trade["position_type"] == "BUY",
                    "blue",
                    "orange"
                ),
            )
        ),
        rx.table.cell(trade["quantity"]),
        rx.table.cell(trade["entry_price"]),
        rx.table.cell(trade["current_price"]),
        rx.table.cell(
            rx.text(
                trade["pnl"],
                # Use pnl_color from trade dict instead of comparison
                color=trade["pnl_color"],
            )
        ),
        rx.table.cell(
            rx.button(
                rx.icon("x", size=14),
                color_scheme="red",
                variant="ghost",
                size="1",
                on_click=GlobalState.close_trade(trade["id"], trade["current_price"]),
            )
        ),
    )


def trades_table() -> rx.Component:
    """Table showing active trades."""
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.heading("Active Positions", size="4", color="white"),
                rx.spacer(),
                rx.button(
                    rx.icon("refresh-cw", size=14),
                    "Refresh",
                    on_click=GlobalState.load_active_trades,
                    variant="ghost",
                    size="1",
                ),
                width="100%",
            ),
            rx.cond(
                GlobalState.has_active_trades,
                rx.table.root(
                    rx.table.header(
                        rx.table.row(
                            rx.table.column_header_cell("Symbol"),
                            rx.table.column_header_cell("Type"),
                            rx.table.column_header_cell("Side"),
                            rx.table.column_header_cell("Qty"),
                            rx.table.column_header_cell("Entry"),
                            rx.table.column_header_cell("LTP"),
                            rx.table.column_header_cell("P&L"),
                            rx.table.column_header_cell("Action"),
                        )
                    ),
                    rx.table.body(
                        rx.foreach(GlobalState.active_trades, trade_row)
                    ),
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("inbox", size=48, color="gray"),
                        rx.text("No active positions", color="gray"),
                        spacing="2",
                        padding="8",
                    ),
                    width="100%",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        style={"background": "rgba(20, 20, 30, 0.8)", "border": "1px solid rgba(255, 255, 255, 0.1)"},
    )


def payoff_chart() -> rx.Component:
    """Payoff diagram chart using recharts."""
    return rx.card(
        rx.vstack(
            rx.heading("Payoff Diagram", size="4", color="white"),
            rx.cond(
                GlobalState.has_active_trades,
                rx.recharts.area_chart(
                    rx.recharts.area(
                        data_key="payoff",
                        stroke="#00bcd4",
                        fill="url(#colorPayoff)",
                    ),
                    rx.recharts.x_axis(data_key="spot"),
                    rx.recharts.y_axis(),
                    rx.recharts.cartesian_grid(stroke_dasharray="3 3"),
                    rx.recharts.graphing_tooltip(),
                    rx.recharts.reference_line(y=0, stroke="gray", stroke_dasharray="3 3"),
                    data=GlobalState.payoff_data,
                    width="100%",
                    height=300,
                ),
                rx.center(
                    rx.text("Add trades to see payoff diagram", color="gray"),
                    height="200px",
                ),
            ),
            spacing="4",
            width="100%",
        ),
        style={"background": "rgba(20, 20, 30, 0.8)", "border": "1px solid rgba(255, 255, 255, 0.1)"},
    )


def ticker_controls() -> rx.Component:
    """WebSocket ticker control buttons."""
    return rx.hstack(
        rx.cond(
            GlobalState.is_ticker_connected,
            rx.button(
                rx.icon("pause", size=14),
                "Stop Ticker",
                on_click=GlobalState.stop_ticker,
                color_scheme="red",
                variant="soft",
            ),
            rx.button(
                rx.icon("play", size=14),
                "Start Ticker",
                on_click=GlobalState.start_ticker,
                color_scheme="green",
                variant="soft",
            ),
        ),
        rx.text(GlobalState.last_tick_time, size="1", color="gray"),
        spacing="4",
        align="center",
    )


def message_toast() -> rx.Component:
    """Toast message display."""
    return rx.cond(
        GlobalState.message != "",
        rx.callout(
            GlobalState.message,
            icon="info",
            color_scheme=rx.cond(
                GlobalState.message_type == "error",
                "red",
                rx.cond(GlobalState.message_type == "success", "green", "blue"),
            ),
        ),
        rx.fragment(),
    )


# ============================================================================
# Pages
# ============================================================================

def index() -> rx.Component:
    """Main dashboard page."""
    return rx.box(
        navbar(),
        rx.container(
            rx.cond(
                GlobalState.is_authenticated,
                rx.vstack(
                    message_toast(),
                    ticker_controls(),
                    market_stats(),
                    rx.grid(
                        trades_table(),
                        payoff_chart(),
                        columns="2",
                        spacing="4",
                        width="100%",
                    ),
                    spacing="6",
                    padding_y="6",
                    width="100%",
                ),
                rx.center(
                    rx.vstack(
                        rx.icon("lock", size=64, color="gray"),
                        rx.heading("Please login to continue", size="5", color="gray"),
                        rx.link(
                            rx.button("Go to Login", color_scheme="cyan", size="3"),
                            href="/login",
                        ),
                        spacing="4",
                        padding="16",
                    ),
                    height="80vh",
                ),
            ),
            max_width="1400px",
            padding="4",
        ),
        background="linear-gradient(180deg, #0a0a0f 0%, #1a1a2e 100%)",
        min_height="100vh",
    )


def login_page() -> rx.Component:
    """Login page for Zerodha authentication - Clean and simple flow."""
    return rx.box(
        navbar(),
        rx.center(
            rx.card(
                rx.vstack(
                    # Header
                    rx.vstack(
                        rx.icon("key", size=48, color="cyan"),
                        rx.heading("Login to KiteCobra", size="6", color="white"),
                        rx.text(
                            "Connect with your Zerodha Kite account",
                            color="gray",
                            size="2",
                        ),
                        spacing="2",
                        align="center",
                    ),

                    rx.divider(),

                    # API Credentials Form
                    rx.form(
                        rx.vstack(
                            # API Key Field
                            rx.vstack(
                                rx.text(
                                    "API Key",
                                    size="2",
                                    weight="medium",
                                    color="white",
                                ),
                                rx.input(
                                    placeholder="Enter your Kite API Key",
                                    value=GlobalState.api_key,
                                    on_change=GlobalState.set_api_key,
                                    size="3",
                                    width="100%",
                                ),
                                spacing="1",
                                width="100%",
                            ),

                            # API Secret Field
                            rx.vstack(
                                rx.text(
                                    "API Secret",
                                    size="2",
                                    weight="medium",
                                    color="white",
                                ),
                                rx.input(
                                    placeholder="Enter your Kite API Secret",
                                    type="password",
                                    value=GlobalState.api_secret,
                                    on_change=GlobalState.set_api_secret,
                                    size="3",
                                    width="100%",
                                ),
                                spacing="1",
                                width="100%",
                            ),

                            spacing="4",
                            width="100%",
                        ),
                    ),

                    # Login Button
                    rx.link(
                        rx.button(
                            rx.hstack(
                                rx.text("Login with Zerodha"),
                                rx.icon("external-link", size=18),
                                spacing="2",
                                align="center",
                            ),
                            color_scheme="cyan",
                            size="3",
                            width="100%",
                            disabled=GlobalState.login_button_disabled,
                        ),
                        href=GlobalState.login_url,
                        is_external=True,
                        width="100%",
                    ),

                    # Info Text
                    rx.text(
                        "You will be redirected to Zerodha for authentication",
                        size="1",
                        color="gray",
                        align="center",
                    ),

                    # Error Messages
                    rx.cond(
                        GlobalState.auth_error != "",
                        rx.callout(
                            GlobalState.auth_error,
                            icon="circle-alert",
                            color_scheme="red",
                            size="1",
                        ),
                    ),

                    # Success/Info Messages
                    rx.cond(
                        GlobalState.message != "",
                        rx.callout(
                            GlobalState.message,
                            icon="info",
                            color_scheme="blue",
                            size="1",
                        ),
                    ),

                    # How to get API credentials
                    rx.divider(),
                    rx.vstack(
                        rx.text(
                            "Don't have API credentials?",
                            size="1",
                            color="gray",
                            weight="medium",
                        ),
                        rx.link(
                            rx.text(
                                "Create Kite Connect App →",
                                size="1",
                                color="cyan",
                            ),
                            href="https://developers.kite.trade/",
                            is_external=True,
                        ),
                        spacing="1",
                        align="center",
                    ),

                    spacing="5",
                    width="100%",
                ),
                max_width="420px",
                padding="8",
                style={
                    "background": "rgba(20, 20, 30, 0.95)",
                    "border": "1px solid rgba(0, 200, 200, 0.3)",
                    "backdrop_filter": "blur(10px)",
                },
            ),
            min_height="85vh",
        ),
        background="linear-gradient(180deg, #0a0a0f 0%, #1a1a2e 100%)",
        min_height="100vh",
    )


def callback_page() -> rx.Component:
    """OAuth callback page - handles redirect from Zerodha."""
    return rx.box(
        navbar(),
        rx.center(
            rx.cond(
                GlobalState.is_authenticated,
                # Success - redirect to dashboard
                rx.vstack(
                    rx.icon("circle-check", size=64, color="green"),
                    rx.heading("Authentication Successful!", size="5", color="white"),
                    rx.text("Redirecting to dashboard...", color="gray"),
                    rx.link(
                        rx.button("Go to Dashboard", color_scheme="cyan"),
                        href="/",
                    ),
                    spacing="4",
                ),
                rx.cond(
                    GlobalState.auth_error != "",
                    # Error state
                    rx.vstack(
                        rx.icon("circle-x", size=64, color="red"),
                        rx.heading("Authentication Failed", size="5", color="white"),
                        rx.text(GlobalState.auth_error, color="red"),
                        rx.link(
                            rx.button("Try Again", color_scheme="cyan"),
                            href="/login",
                        ),
                        spacing="4",
                    ),
                    # Loading state
                    rx.vstack(
                        rx.spinner(size="3"),
                        rx.text("Processing authentication...", color="gray"),
                        rx.text(
                            "Request token received. Complete authentication on login page.",
                            color="gray",
                            size="1",
                        ),
                        rx.link(
                            rx.button("Complete on Login Page", color_scheme="cyan", size="2"),
                            href="/login",
                        ),
                        spacing="4",
                    ),
                ),
            ),
            height="80vh",
        ),
        on_mount=GlobalState.handle_callback_redirect,
        background="linear-gradient(180deg, #0a0a0f 0%, #1a1a2e 100%)",
        min_height="100vh",
    )


# ============================================================================
# App Configuration
# ============================================================================

# Create the app
app = rx.App(
    theme=rx.theme(
        appearance="dark",
        accent_color="cyan",
        radius="medium",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ],
)

# Add pages
app.add_page(index, route="/", title="KiteCobra - Paper Trading")
app.add_page(login_page, route="/login", title="Login - KiteCobra")
app.add_page(callback_page, route="/callback", title="Authenticating...")
