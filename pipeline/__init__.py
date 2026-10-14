"""Travguiden – datapipeline för lördagens V-spel (V85, och V75 från 28 november 2026)."""
import warnings

# macOS systempython är byggd mot LibreSSL; ofarligt för oss men brusigt i loggen.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
