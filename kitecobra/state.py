"""
KiteCobra State Management

This module defines the Trade model and GlobalState class for managing
Kite Connect sessions and real-time WebSocket ticker updates.

References:
- Kite Python Docs: https://kite.trade/docs/pykiteconnect/v4/
- Kite WebSocket: https://kite.trade/docs/connect/v3/websocket/
- Reflex Docs: https://reflex.dev/docs/getting-started/introduction/
"""

import reflex as rx
from sqlmodel import Field, Relationship
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from enum import Enum
import asyncio
import threading
from decimal import Decimal


# ============================================================================
# Database Models (SQLModel)
# ============================================================================

class OptionType(str, Enum):
    """Option type enumeration."""
    CALL = "CE"
    PUT = "PE"


class PositionType(str, Enum):
    """Position type enumeration."""
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, Enum):
    """Trade status enumeration."""
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    EXPIRED = "EXPIRED"


class Trade(rx.Model, table=True):
    """
    Trade model representing a single leg of an options strategy.

    Stores virtual trades for paper trading including strike price,
    expiry date, quantity, entry price, and current market data.
    """

    # Primary key
    id: Optional[int] = Field(default=None, primary_key=True)

    # Strategy grouping - trades with same strategy_id form a strategy
    strategy_id: str = Field(index=True)
    strategy_name: Optional[str] = Field(default=None)

    # Instrument details
    symbol: str = Field(index=True)  # NIFTY or BANKNIFTY or SENSEX
    instrument_token: int = Field(index=True)  # Kite instrument token for WebSocket
    tradingsymbol: str = Field(index=True)  # Full trading symbol e.g., NIFTY24JAN22000CE
    exchange: str = Field(default="NFO")  # NFO for options

    # Option details
    strike_price: float
    expiry_date: date
    option_type: str  # CE or PE

    # Position details
    position_type: str  # BUY or SELL
    quantity: int  # Lot size * number of lots
    lot_size: int = Field(default=50)  # NIFTY=50, BANKNIFTY=15, SENSEX=10

    # Pricing
    entry_price: float  # Entry price per unit
    current_price: float = Field(default=0.0)  # Last traded price (updated via WebSocket)
    exit_price: Optional[float] = Field(default=None)  # Exit price if closed

    # Status
    status: str = Field(default=TradeStatus.ACTIVE.value)

    # Timestamps
    entry_time: datetime = Field(default_factory=datetime.utcnow)
    exit_time: Optional[datetime] = Field(default=None)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Virtual cash tracking
    margin_used: float = Field(default=0.0)  # Margin blocked for this trade

    @property
    def pnl(self) -> float:
        """Calculate current P&L for this leg."""
        multiplier = 1 if self.position_type == PositionType.BUY.value else -1
        price_diff = self.current_price - self.entry_price
        return multiplier * price_diff * self.quantity

    @property
    def pnl_percentage(self) -> float:
        """Calculate P&L as percentage of entry value."""
        entry_value = self.entry_price * self.quantity
        if entry_value == 0:
            return 0.0
        return (self.pnl / entry_value) * 100

    @property
    def is_itm(self) -> bool:
        """Check if option is In-The-Money (requires spot price)."""
        # This would need spot price to calculate properly
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert trade to dictionary for UI display."""
        pnl_value = round(self.pnl, 2)
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "tradingsymbol": self.tradingsymbol,
            "instrument_token": self.instrument_token,
            "strike_price": self.strike_price,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "option_type": self.option_type,
            "position_type": self.position_type,
            "quantity": self.quantity,
            "entry_price": round(self.entry_price, 2),
            "current_price": round(self.current_price, 2),
            "pnl": pnl_value,
            "pnl_color": "green" if pnl_value >= 0 else "red",
            "pnl_percentage": round(self.pnl_percentage, 2),
            "status": self.status,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
        }


class VirtualAccount(rx.Model, table=True):
    """
    Virtual account for paper trading.
    Tracks virtual cash and overall P&L.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(unique=True, index=True)

    # Virtual cash
    initial_capital: float = Field(default=1000000.0)  # 10 Lakhs default
    available_margin: float = Field(default=1000000.0)
    used_margin: float = Field(default=0.0)

    # P&L tracking
    realized_pnl: float = Field(default=0.0)
    unrealized_pnl: float = Field(default=0.0)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# Kite Connect Configuration
# ============================================================================

class KiteConfig:
    """Configuration for Kite Connect API."""

    # Login URL for OAuth flow
    LOGIN_URL = "https://kite.zerodha.com/connect/login"

    # API endpoints
    API_BASE_URL = "https://api.kite.trade"

    # Index instrument tokens (for spot price tracking)
    INSTRUMENT_TOKENS = {
        "NIFTY 50": 256265,      # NSE index
        "NIFTY BANK": 260105,    # NSE index
        "SENSEX": 265,           # BSE index
    }

    # Lot sizes
    LOT_SIZES = {
        "NIFTY": 50,
        "BANKNIFTY": 15,
        "SENSEX": 10,
    }

    # Exchange segments
    EXCHANGE_NFO = "NFO"
    EXCHANGE_BFO = "BFO"  # BSE F&O for SENSEX


# ============================================================================
# Global State Class
# ============================================================================

class GlobalState(rx.State):
    """
    Global application state managing Kite Connect session and real-time data.

    This state class handles:
    1. Kite Connect authentication (API key, secret, access token)
    2. WebSocket connection management via background task
    3. Real-time LTP and P&L updates
    4. Trade management (add, modify, close)
    """

    # -------------------------------------------------------------------------
    # Authentication State
    # -------------------------------------------------------------------------

    api_key: str = ""
    api_secret: str = ""
    request_token: str = ""
    access_token: str = ""

    # User info from Kite
    user_id: str = ""
    user_name: str = ""
    user_email: str = ""

    # Auth status
    is_authenticated: bool = False
    auth_error: str = ""
    is_loading: bool = False

    # -------------------------------------------------------------------------
    # WebSocket State
    # -------------------------------------------------------------------------

    is_ticker_connected: bool = False
    ticker_status: str = "Disconnected"
    last_tick_time: str = ""

    # -------------------------------------------------------------------------
    # Market Data State (updated by WebSocket)
    # -------------------------------------------------------------------------

    # Spot prices for indices
    nifty_spot: float = 0.0
    banknifty_spot: float = 0.0
    sensex_spot: float = 0.0

    # LTP cache: instrument_token -> LTP
    # Using dict for reactive updates
    ltp_cache: Dict[str, float] = {}

    # -------------------------------------------------------------------------
    # Trade State
    # -------------------------------------------------------------------------

    # Active trades as list of dicts for UI display
    active_trades: List[Dict[str, Any]] = []

    # Total P&L
    total_pnl: float = 0.0
    total_pnl_percentage: float = 0.0

    # Virtual account
    available_margin: float = 1000000.0
    used_margin: float = 0.0

    # -------------------------------------------------------------------------
    # UI State
    # -------------------------------------------------------------------------

    selected_symbol: str = "NIFTY"
    selected_expiry: str = ""
    available_expiries: List[str] = []

    # Form state for adding trades
    add_trade_strike: str = ""
    add_trade_option_type: str = "CE"
    add_trade_position_type: str = "BUY"
    add_trade_lots: int = 1
    add_trade_price: str = ""

    # Error/success messages
    message: str = ""
    message_type: str = ""  # "success", "error", "info"

    # -------------------------------------------------------------------------
    # Kite Connect Instance (non-reactive, managed separately)
    # -------------------------------------------------------------------------

    # Note: The actual KiteConnect and KiteTicker instances are managed
    # in a separate module to avoid serialization issues with Reflex state.
    # We use class-level variables or a separate singleton pattern.

    _kite_instance = None
    _ticker_instance = None
    _ticker_thread = None
    _should_stop_ticker: bool = False

    # -------------------------------------------------------------------------
    # Authentication Methods
    # -------------------------------------------------------------------------

    def set_api_key(self, value: str):
        """Set API key from input."""
        self.api_key = value
        self.auth_error = ""

    def set_api_secret(self, value: str):
        """Set API secret from input."""
        self.api_secret = value
        self.auth_error = ""

    def set_request_token(self, value: str):
        """Set request token from input."""
        self.request_token = value.strip()

    async def handle_callback_redirect(self):
        """
        Handle the OAuth callback redirect from Zerodha.
        Extracts request_token from URL query params and processes authentication.
        """
        # Get request_token from URL query parameters
        # Try multiple methods to get the params
        request_token = ""

        try:
            # Method 1: Try router.page.params (Reflex standard)
            params = self.router.page.params
            request_token = params.get("request_token", "")
        except Exception:
            pass

        if not request_token:
            try:
                # Method 2: Try router.page.raw_path parsing
                raw_path = getattr(self.router.page, 'raw_path', '')
                if 'request_token=' in raw_path:
                    import urllib.parse
                    parsed = urllib.parse.urlparse(raw_path)
                    query_params = urllib.parse.parse_qs(parsed.query)
                    request_token = query_params.get('request_token', [''])[0]
            except Exception:
                pass

        if request_token:
            self.request_token = request_token
            self.message = f"Request token received: {request_token[:10]}..."
            self.message_type = "info"

            # Auto-process if we have API credentials stored
            if self.api_key and self.api_secret:
                await self.handle_request_token()
            else:
                # Redirect to login page with token pre-filled
                self.message = "Request token received. Please enter API credentials on login page."
                self.message_type = "info"
                return rx.redirect("/login")
        else:
            self.message = "No request token found in callback URL"
            self.message_type = "error"

    def set_api_credentials(self, api_key: str, api_secret: str):
        """Set API credentials from login form."""
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.auth_error = ""

    def get_login_url(self) -> str:
        """Generate Kite Connect login URL for OAuth flow."""
        if not self.api_key:
            return ""
        return f"{KiteConfig.LOGIN_URL}?api_key={self.api_key}&v=3"

    @rx.var
    def login_url(self) -> str:
        """Computed var for login URL."""
        if not self.api_key:
            return ""
        return f"{KiteConfig.LOGIN_URL}?api_key={self.api_key}&v=3"

    async def handle_request_token(self):
        """
        Handle the request_token from Zerodha redirect.
        Exchange it for access_token using Kite Connect API.
        """
        self.is_loading = True
        self.auth_error = ""

        if not self.request_token:
            self.auth_error = "Please enter the request token"
            self.is_loading = False
            return

        try:
            # Import here to avoid issues if kiteconnect not installed
            from kiteconnect import KiteConnect

            # Create Kite instance
            kite = KiteConnect(api_key=self.api_key)

            # Generate session (exchange request_token for access_token)
            data = kite.generate_session(
                request_token=self.request_token,
                api_secret=self.api_secret
            )

            # Store access token
            self.access_token = data["access_token"]
            kite.set_access_token(self.access_token)

            # Get user profile
            profile = kite.profile()
            self.user_id = profile.get("user_id", "")
            self.user_name = profile.get("user_name", "")
            self.user_email = profile.get("email", "")

            # Store kite instance for later use
            GlobalState._kite_instance = kite

            self.is_authenticated = True
            self.message = "Successfully authenticated with Zerodha!"
            self.message_type = "success"

            # Initialize virtual account if not exists
            await self._init_virtual_account()

            # Load active trades
            await self.load_active_trades()

        except Exception as e:
            self.auth_error = f"Authentication failed: {str(e)}"
            self.message = self.auth_error
            self.message_type = "error"
            self.is_authenticated = False
        finally:
            self.is_loading = False

    async def _init_virtual_account(self):
        """Initialize virtual account for the user."""
        with rx.session() as session:
            # Check if account exists
            existing = session.exec(
                VirtualAccount.select().where(
                    VirtualAccount.user_id == self.user_id
                )
            ).first()

            if not existing:
                # Create new virtual account
                account = VirtualAccount(
                    user_id=self.user_id,
                    initial_capital=1000000.0,
                    available_margin=1000000.0,
                    used_margin=0.0,
                )
                session.add(account)
                session.commit()
                self.available_margin = account.available_margin
            else:
                self.available_margin = existing.available_margin
                self.used_margin = existing.used_margin

    def logout(self):
        """Logout and cleanup."""
        self.stop_ticker()

        self.api_key = ""
        self.api_secret = ""
        self.request_token = ""
        self.access_token = ""
        self.user_id = ""
        self.user_name = ""
        self.user_email = ""
        self.is_authenticated = False
        self.is_ticker_connected = False

        GlobalState._kite_instance = None
        GlobalState._ticker_instance = None

    # -------------------------------------------------------------------------
    # WebSocket Ticker Methods
    # -------------------------------------------------------------------------

    def start_ticker(self):
        """
        Start the KiteTicker WebSocket connection in a background thread.

        This method spawns a daemon thread that maintains the WebSocket
        connection and processes ticks to update LTP and P&L values.
        """
        if not self.access_token or not self.api_key:
            self.message = "Cannot start ticker: Not authenticated"
            self.message_type = "error"
            return

        if self.is_ticker_connected:
            self.message = "Ticker already running"
            self.message_type = "info"
            return

        try:
            from kiteconnect import KiteTicker

            tokens_to_subscribe = self._get_subscription_tokens()

            if not tokens_to_subscribe:
                self.message = "No instruments to subscribe"
                self.message_type = "info"
                return

            # Create ticker instance
            ticker = KiteTicker(self.api_key, self.access_token)
            GlobalState._ticker_instance = ticker
            GlobalState._should_stop_ticker = False

            # Store state reference for callbacks
            state_ref = self

            def on_connect(ws, response):
                """Callback on WebSocket connect."""
                ws.subscribe(tokens_to_subscribe)
                ws.set_mode(ws.MODE_LTP, tokens_to_subscribe)

            def on_ticks(ws, ticks):
                """Callback on receiving ticks."""
                # Process ticks - updates are stored in class-level cache
                state_ref._process_ticks_sync(ticks)

            def on_close(ws, code, reason):
                """Callback on WebSocket close."""
                GlobalState._should_stop_ticker = True

            def on_error(ws, code, reason):
                """Callback on WebSocket error."""
                pass

            # Assign callbacks
            ticker.on_connect = on_connect
            ticker.on_ticks = on_ticks
            ticker.on_close = on_close
            ticker.on_error = on_error

            self.is_ticker_connected = True
            self.ticker_status = "Connected"
            self.message = "WebSocket ticker started"
            self.message_type = "success"

            # Start ticker in a daemon thread
            def run_ticker():
                try:
                    ticker.connect(threaded=False)
                except Exception:
                    pass

            ticker_thread = threading.Thread(target=run_ticker, daemon=True)
            ticker_thread.start()
            GlobalState._ticker_thread = ticker_thread

        except ImportError:
            self.message = "kiteconnect package not installed"
            self.message_type = "error"
        except Exception as e:
            self.message = f"Ticker error: {str(e)}"
            self.message_type = "error"
            self.is_ticker_connected = False
            self.ticker_status = "Error"

    def stop_ticker(self):
        """Stop the WebSocket ticker."""
        GlobalState._should_stop_ticker = True

        if GlobalState._ticker_instance:
            try:
                GlobalState._ticker_instance.close()
            except:
                pass
            GlobalState._ticker_instance = None

        self.is_ticker_connected = False
        self.ticker_status = "Disconnected"
        self.message = "WebSocket ticker stopped"
        self.message_type = "info"

    def _get_subscription_tokens(self) -> List[int]:
        """Get list of instrument tokens to subscribe."""
        tokens = set()

        # Add index tokens for spot prices
        tokens.add(KiteConfig.INSTRUMENT_TOKENS["NIFTY 50"])
        tokens.add(KiteConfig.INSTRUMENT_TOKENS["NIFTY BANK"])

        # Add tokens from active trades
        for trade in self.active_trades:
            if trade.get("instrument_token"):
                tokens.add(trade["instrument_token"])

        return list(tokens)

    def _process_ticks_sync(self, ticks: List[Dict]):
        """
        Process incoming ticks (called from ticker thread).

        Note: This is called from a non-async context.
        We update class-level variables which will be synced to state.
        """
        for tick in ticks:
            token = tick.get("instrument_token")
            ltp = tick.get("last_price", 0.0)

            if token is None:
                continue

            # Update spot prices
            if token == KiteConfig.INSTRUMENT_TOKENS["NIFTY 50"]:
                self.nifty_spot = ltp
            elif token == KiteConfig.INSTRUMENT_TOKENS["NIFTY BANK"]:
                self.banknifty_spot = ltp

            # Update LTP cache
            self.ltp_cache[str(token)] = ltp

        # Recalculate P&L
        self._update_pnl()

    def _update_pnl(self):
        """Update P&L for all active trades based on current LTP."""
        total_pnl = 0.0
        total_entry_value = 0.0

        updated_trades = []
        for trade in self.active_trades:
            token = str(trade.get("instrument_token", ""))
            current_ltp = self.ltp_cache.get(token, trade.get("current_price", 0.0))

            # Update current price
            trade["current_price"] = round(current_ltp, 2)

            # Calculate P&L
            entry_price = trade.get("entry_price", 0.0)
            quantity = trade.get("quantity", 0)
            position_type = trade.get("position_type", "BUY")

            multiplier = 1 if position_type == "BUY" else -1
            pnl = multiplier * (current_ltp - entry_price) * quantity
            pnl_rounded = round(pnl, 2)

            trade["pnl"] = pnl_rounded
            trade["pnl_color"] = "green" if pnl_rounded >= 0 else "red"

            entry_value = entry_price * quantity
            if entry_value > 0:
                trade["pnl_percentage"] = round((pnl / entry_value) * 100, 2)

            total_pnl += pnl
            total_entry_value += entry_value

            updated_trades.append(trade)

        self.active_trades = updated_trades
        self.total_pnl = round(total_pnl, 2)

        if total_entry_value > 0:
            self.total_pnl_percentage = round((total_pnl / total_entry_value) * 100, 2)

    # -------------------------------------------------------------------------
    # Trade Management Methods
    # -------------------------------------------------------------------------

    async def load_active_trades(self):
        """Load active trades from database."""
        with rx.session() as session:
            trades = session.exec(
                Trade.select().where(Trade.status == TradeStatus.ACTIVE.value)
            ).all()

            self.active_trades = [trade.to_dict() for trade in trades]

        # Update P&L with current prices
        self._update_pnl()

    async def add_trade(
        self,
        symbol: str,
        strike_price: float,
        expiry_date: date,
        option_type: str,
        position_type: str,
        lots: int,
        entry_price: float,
        instrument_token: int,
        tradingsymbol: str,
        strategy_id: Optional[str] = None,
        strategy_name: Optional[str] = None,
    ):
        """Add a new trade leg to the database."""
        import uuid

        # Get lot size
        lot_size = KiteConfig.LOT_SIZES.get(symbol, 50)
        quantity = lots * lot_size

        # Generate strategy ID if not provided
        if not strategy_id:
            strategy_id = str(uuid.uuid4())[:8]

        # Calculate margin (simplified - actual margin calc is complex)
        margin_required = entry_price * quantity * 0.2  # 20% margin approximation

        if margin_required > self.available_margin:
            self.message = f"Insufficient margin. Required: {margin_required:.2f}, Available: {self.available_margin:.2f}"
            self.message_type = "error"
            return

        # Create trade
        with rx.session() as session:
            trade = Trade(
                strategy_id=strategy_id,
                strategy_name=strategy_name or f"{symbol} Trade",
                symbol=symbol,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange="NFO" if symbol != "SENSEX" else "BFO",
                strike_price=strike_price,
                expiry_date=expiry_date,
                option_type=option_type,
                position_type=position_type,
                quantity=quantity,
                lot_size=lot_size,
                entry_price=entry_price,
                current_price=entry_price,
                margin_used=margin_required,
                status=TradeStatus.ACTIVE.value,
            )
            session.add(trade)
            session.commit()
            session.refresh(trade)

            # Update margin
            self.available_margin -= margin_required
            self.used_margin += margin_required

            # Update virtual account
            account = session.exec(
                VirtualAccount.select().where(VirtualAccount.user_id == self.user_id)
            ).first()
            if account:
                account.available_margin = self.available_margin
                account.used_margin = self.used_margin
                session.add(account)
                session.commit()

            # Add to active trades
            self.active_trades.append(trade.to_dict())

        self.message = f"Trade added: {tradingsymbol}"
        self.message_type = "success"

        # If ticker is running, subscribe to new token
        if self.is_ticker_connected and GlobalState._ticker_instance:
            try:
                GlobalState._ticker_instance.subscribe([instrument_token])
                GlobalState._ticker_instance.set_mode(
                    GlobalState._ticker_instance.MODE_LTP,
                    [instrument_token]
                )
            except:
                pass

    async def close_trade(self, trade_id: int, exit_price: float):
        """Close a trade and calculate final P&L."""
        with rx.session() as session:
            trade = session.get(Trade, trade_id)

            if not trade:
                self.message = "Trade not found"
                self.message_type = "error"
                return

            # Calculate final P&L
            multiplier = 1 if trade.position_type == PositionType.BUY.value else -1
            final_pnl = multiplier * (exit_price - trade.entry_price) * trade.quantity

            # Update trade
            trade.exit_price = exit_price
            trade.current_price = exit_price
            trade.status = TradeStatus.CLOSED.value
            trade.exit_time = datetime.utcnow()

            session.add(trade)

            # Release margin and update account
            self.available_margin += trade.margin_used + final_pnl
            self.used_margin -= trade.margin_used

            account = session.exec(
                VirtualAccount.select().where(VirtualAccount.user_id == self.user_id)
            ).first()
            if account:
                account.available_margin = self.available_margin
                account.used_margin = self.used_margin
                account.realized_pnl += final_pnl
                session.add(account)

            session.commit()

        # Remove from active trades
        self.active_trades = [t for t in self.active_trades if t.get("id") != trade_id]

        self._update_pnl()

        self.message = f"Trade closed. P&L: {final_pnl:.2f}"
        self.message_type = "success" if final_pnl >= 0 else "error"

    async def close_all_trades(self):
        """Close all active trades at current market prices."""
        for trade in self.active_trades.copy():
            trade_id = trade.get("id")
            current_price = trade.get("current_price", trade.get("entry_price", 0))
            if trade_id:
                await self.close_trade(trade_id, current_price)

    # -------------------------------------------------------------------------
    # Instrument Search Methods
    # -------------------------------------------------------------------------

    async def search_instruments(self, symbol: str, expiry: str, strike: float, option_type: str):
        """
        Search for instrument token using Kite API.
        Returns instrument details including token.
        """
        if not GlobalState._kite_instance:
            self.message = "Not connected to Kite"
            self.message_type = "error"
            return None

        try:
            # Get instruments from Kite
            instruments = GlobalState._kite_instance.instruments("NFO")

            # Filter by criteria
            for inst in instruments:
                if (inst["name"] == symbol and
                    inst["strike"] == strike and
                    inst["instrument_type"] == option_type and
                    str(inst["expiry"]) == expiry):
                    return {
                        "instrument_token": inst["instrument_token"],
                        "tradingsymbol": inst["tradingsymbol"],
                        "lot_size": inst["lot_size"],
                        "expiry": inst["expiry"],
                    }

            return None

        except Exception as e:
            self.message = f"Instrument search error: {str(e)}"
            self.message_type = "error"
            return None

    async def get_available_expiries(self, symbol: str):
        """Get available expiry dates for a symbol."""
        if not GlobalState._kite_instance:
            self.available_expiries = []
            return

        try:
            exchange = "NFO" if symbol != "SENSEX" else "BFO"
            instruments = GlobalState._kite_instance.instruments(exchange)

            # Get unique expiries for the symbol
            expiries = set()
            for inst in instruments:
                if inst["name"] == symbol and inst["instrument_type"] in ["CE", "PE"]:
                    expiries.add(str(inst["expiry"]))

            self.available_expiries = sorted(list(expiries))[:10]  # Next 10 expiries

        except Exception as e:
            self.available_expiries = []

    # -------------------------------------------------------------------------
    # Payoff Calculation Methods
    # -------------------------------------------------------------------------

    def calculate_payoff(self, spot_range: List[float]) -> Dict[str, List[float]]:
        """
        Calculate strategy payoff at expiry for given spot price range.

        Returns dict with:
        - spot_prices: List of spot prices
        - payoffs: List of corresponding payoff values
        - breakeven: List of breakeven points
        """
        payoffs = []

        for spot in spot_range:
            total_payoff = 0.0

            for trade in self.active_trades:
                strike = trade.get("strike_price", 0)
                option_type = trade.get("option_type", "CE")
                position_type = trade.get("position_type", "BUY")
                quantity = trade.get("quantity", 0)
                entry_price = trade.get("entry_price", 0)

                # Calculate intrinsic value at expiry
                if option_type == "CE":
                    intrinsic = max(0, spot - strike)
                else:  # PE
                    intrinsic = max(0, strike - spot)

                # Calculate P&L for this leg
                if position_type == "BUY":
                    leg_pnl = (intrinsic - entry_price) * quantity
                else:  # SELL
                    leg_pnl = (entry_price - intrinsic) * quantity

                total_payoff += leg_pnl

            payoffs.append(total_payoff)

        # Find breakeven points (where payoff crosses zero)
        breakevens = []
        for i in range(1, len(payoffs)):
            if (payoffs[i-1] < 0 and payoffs[i] >= 0) or (payoffs[i-1] >= 0 and payoffs[i] < 0):
                # Linear interpolation to find exact breakeven
                ratio = abs(payoffs[i-1]) / (abs(payoffs[i-1]) + abs(payoffs[i]))
                breakeven = spot_range[i-1] + ratio * (spot_range[i] - spot_range[i-1])
                breakevens.append(round(breakeven, 2))

        return {
            "spot_prices": spot_range,
            "payoffs": [round(p, 2) for p in payoffs],
            "breakevens": breakevens,
        }

    @rx.var
    def payoff_data(self) -> List[Dict[str, float]]:
        """Computed var for payoff chart data."""
        if not self.active_trades:
            return []

        # Determine spot range based on current index price and strikes
        strikes = [t.get("strike_price", 0) for t in self.active_trades]
        if not strikes:
            return []

        center = self.nifty_spot if self.nifty_spot > 0 else sum(strikes) / len(strikes)
        min_spot = center * 0.9  # 10% below
        max_spot = center * 1.1  # 10% above

        # Generate spot range
        step = (max_spot - min_spot) / 100
        spot_range = [min_spot + i * step for i in range(101)]

        # Calculate payoff
        result = self.calculate_payoff(spot_range)

        # Format for recharts
        return [
            {"spot": spot, "payoff": payoff}
            for spot, payoff in zip(result["spot_prices"], result["payoffs"])
        ]

    # -------------------------------------------------------------------------
    # Computed Variables
    # -------------------------------------------------------------------------

    @rx.var
    def can_login(self) -> bool:
        """Check if user can initiate login (has both API key and secret)."""
        return len(self.api_key.strip()) > 0 and len(self.api_secret.strip()) > 0

    @rx.var
    def login_button_disabled(self) -> bool:
        """Returns True if login button should be disabled."""
        return not self.can_login

    @rx.var
    def formatted_nifty_spot(self) -> str:
        """Formatted NIFTY spot price."""
        return f"{self.nifty_spot:,.2f}" if self.nifty_spot > 0 else "--"

    @rx.var
    def formatted_banknifty_spot(self) -> str:
        """Formatted Bank NIFTY spot price."""
        return f"{self.banknifty_spot:,.2f}" if self.banknifty_spot > 0 else "--"

    @rx.var
    def formatted_total_pnl(self) -> str:
        """Formatted total P&L with color indicator."""
        return f"{'+'if self.total_pnl >= 0 else ''}{self.total_pnl:,.2f}"

    @rx.var
    def pnl_color(self) -> str:
        """Color for P&L display."""
        if self.total_pnl > 0:
            return "green"
        elif self.total_pnl < 0:
            return "red"
        return "gray"

    @rx.var
    def formatted_margin(self) -> str:
        """Formatted available margin."""
        return f"{self.available_margin:,.2f}"

    @rx.var
    def has_active_trades(self) -> bool:
        """Check if there are active trades."""
        return len(self.active_trades) > 0
