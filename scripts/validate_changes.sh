#!/bin/bash

# Thronos Chain - Pre-Commit Validation Script
# Purpose: Catch common mistakes before they break production
# Usage: ./scripts/validate_changes.sh

set -e  # Exit on error

echo "🔍 Thronos Chain - Pre-Commit Validation"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
ERRORS=0
WARNINGS=0

# Function to report error
error() {
    echo -e "${RED}❌ ERROR: $1${NC}"
    ERRORS=$((ERRORS + 1))
}

# Function to report warning
warn() {
    echo -e "${YELLOW}⚠️  WARNING: $1${NC}"
    WARNINGS=$((WARNINGS + 1))
}

# Function to report success
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

echo "📋 Running validation checks..."
echo ""

# Check 1: Verify critical files exist
echo "1️⃣  Checking critical files..."
CRITICAL_FILES=(
    "templates/base.html"
    "static/wallet_session.js"
    "server.py"
)

for file in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        error "Critical file missing: $file"
    else
        success "Found $file"
    fi
done
echo ""

# Check 2: Validate HTML structure in base.html
echo "2️⃣  Validating base.html structure..."

# Check for critical element IDs
REQUIRED_IDS=(
    "walletUnifiedBtn"
    "walletStatus"
    "walletBalancePopup"
    "walletModalOverlay"
    "walletWidgetAddress"
    "walletWidgetSecret"
    "walletWidgetPin"
    "sendModal"
    "receiveModal"
    "tokenInfoModal"
)

for id in "${REQUIRED_IDS[@]}"; do
    if ! grep -q "id=\"$id\"" templates/base.html; then
        error "Missing element in base.html: id=\"$id\""
    else
        success "Found element: id=\"$id\""
    fi
done
echo ""

# Check 3: Validate wallet_session.js
echo "3️⃣  Validating wallet_session.js..."

# Check for required functions
REQUIRED_FUNCTIONS=(
    "getAddress"
    "setAddress"
    "getSendSeed"
    "setSendSeed"
    "isBound"
    "setBound"
    "clearSession"
    "saveSession"
    "requirePin"
)

for func in "${REQUIRED_FUNCTIONS[@]}"; do
    if ! grep -q "function $func" static/wallet_session.js && ! grep -q "$func:" static/wallet_session.js; then
        error "Missing function in wallet_session.js: $func"
    else
        success "Found function: $func"
    fi
done

# Check walletSession is exported
if ! grep -q "window.walletSession" static/wallet_session.js; then
    error "walletSession not exported to window object"
else
    success "walletSession exported to window"
fi
echo ""

# Check 4: Validate JavaScript syntax
echo "4️⃣  Checking JavaScript syntax..."

# Check for common syntax errors in base.html
if grep -q "function.*function" templates/base.html; then
    warn "Possible nested function definition (check syntax)"
fi

if grep -q "getElementById(\"[^\"]*\")[^;]*getElementById" templates/base.html; then
    warn "Multiple getElementById calls in one line (might be fragile)"
fi

# Check for missing semicolons before closing braces
if grep -P "[a-zA-Z0-9]\n\s*}" templates/base.html > /dev/null 2>&1; then
    warn "Possible missing semicolon before closing brace"
fi

success "JavaScript syntax checks passed"
echo ""

# Check 5: Validate CSS selectors are used correctly
echo "5️⃣  Validating CSS..."

# Check .wallet-status.open rule exists
if ! grep -q "\.wallet-status\.open" templates/base.html; then
    error "Missing CSS rule: .wallet-status.open .wallet-balance-popup"
fi

# Check z-index for navbar
if ! grep -q "z-index.*1500" templates/base.html; then
    warn "Navbar z-index might not be set correctly"
fi

# Check z-index for dropdown
if ! grep -q "z-index.*2000" templates/base.html; then
    warn "Dropdown z-index might not be set correctly"
fi

success "CSS validation passed"
echo ""

# Check 6: Validate no direct style.display manipulation
echo "6️⃣  Checking for anti-patterns..."

# Check for direct popup.style.display usage (should use setWalletOpen)
if grep -q "popup\.style\.display\s*=" templates/base.html; then
    warn "Found direct popup.style.display manipulation - should use setWalletOpen()"
fi

# Check for walletLoginSection references OUTSIDE the modal (shouldn't exist in popup)
# walletLoginSection is OK inside the modal, but not in the popup
if grep -A5 "walletBalancePopup" templates/base.html | grep -q "walletLoginSection"; then
    error "Found walletLoginSection inside wallet popup (should only be in modal)"
fi

success "Anti-pattern checks passed"
echo ""

# Check 7: Validate API endpoints in server.py
echo "7️⃣  Validating API endpoints..."

REQUIRED_ENDPOINTS=(
    "@app.route(\"/api/bridge/status\")"
    "@app.route(\"/api/wallet/tokens"
    "@app.route(\"/api/network_stats\")"
)

for endpoint in "${REQUIRED_ENDPOINTS[@]}"; do
    if ! grep -q "$endpoint" server.py; then
        warn "API endpoint might be missing: $endpoint"
    else
        success "Found endpoint: $endpoint"
    fi
done
echo ""

# Check 8: Git diff safety check
echo "8️⃣  Reviewing git changes..."

if git diff --cached --name-only | grep -q "base.html\|wallet_session.js"; then
    echo -e "${YELLOW}⚠️  You're modifying critical wallet files!${NC}"
    echo "   Changed files:"
    git diff --cached --name-only | grep "base.html\|wallet_session.js" | sed 's/^/   - /'
    echo ""

    # Check for deletions
    DELETIONS=$(git diff --cached --numstat | awk '{deleted+=$2} END {print deleted}')
    ADDITIONS=$(git diff --cached --numstat | awk '{added+=$1} END {print added}')

    echo "   Lines added: $ADDITIONS"
    echo "   Lines deleted: $DELETIONS"
    echo ""

    if [ "$DELETIONS" -gt 50 ]; then
        warn "Large number of deletions ($DELETIONS lines) - verify you didn't remove critical code"
    fi
fi
echo ""

# Check 9: Node dependencies (if any)
echo "9️⃣  Checking dependencies..."

if [ -f "package.json" ]; then
    if command -v npm &> /dev/null; then
        npm outdated || warn "Some npm packages are outdated"
    fi
fi

success "Dependency check complete"
echo ""

# Summary
echo "=========================================="
echo "📊 Validation Summary"
echo "=========================================="
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}🎉 All checks passed! You're good to commit.${NC}"
    echo ""
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  $WARNINGS warning(s) found, but no errors.${NC}"
    echo ""
    echo "You can proceed, but review warnings carefully."
    exit 0
else
    echo -e "${RED}❌ Found $ERRORS error(s) and $WARNINGS warning(s).${NC}"
    echo ""
    echo "🚨 DO NOT COMMIT until errors are fixed!"
    echo ""
    echo "Common fixes:"
    echo "  - Restore deleted elements/functions"
    echo "  - Check typos in element IDs"
    echo "  - Verify all required files exist"
    echo ""
    exit 1
fi
