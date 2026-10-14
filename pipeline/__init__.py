"""Travguiden – datapipeline för V85."""
import warnings

# macOS systempython är byggd mot LibreSSL; ofarligt för oss men brusigt i loggen.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
