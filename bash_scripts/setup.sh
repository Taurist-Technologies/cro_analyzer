#!/bin/bash

# CRO Analyzer Setup Script
# This script sets up the entire environment for the CRO Analyzer service

set -e  # Exit on any error

echo "🚀 CRO Analyzer Setup Script"
echo "=============================="
echo ""

# Check Python version
echo "📋 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Found Python $python_version"

# Check if we're in a virtual environment
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo ""
    echo "⚠️  No virtual environment detected"
    echo "   Creating virtual environment..."
    python3 -m venv venv
    echo "   ✅ Virtual environment created"
    echo ""
    echo "   Please activate it with:"
    echo "   source venv/bin/activate"
    echo ""
    echo "   Then run this script again."
    exit 0
fi

echo "   ✅ Virtual environment active"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt
echo "   ✅ Dependencies installed"
echo ""

# Install Playwright browsers
echo "🌐 Installing Playwright browsers..."
playwright install chromium
echo "   ✅ Playwright browsers installed"
echo ""

# Check for Anthropic API key
echo "🔑 Checking for Anthropic API key..."
if [[ -z "$ANTHROPIC_API_KEY" ]]; then
    echo "   ⚠️  ANTHROPIC_API_KEY not found in environment"
    echo ""
    echo "   Please set your API key:"
    echo "   export ANTHROPIC_API_KEY='your-api-key-here'"
    echo ""
    echo "   Or create a .env file with:"
    echo "   ANTHROPIC_API_KEY=your-api-key-here"
    echo ""
    echo "   Get your API key from: https://console.anthropic.com/"
else
    echo "   ✅ API key found"
fi
echo ""

# Done
echo "✅ Setup complete!"
echo ""
echo "📖 Next steps:"
echo "   1. Set ANTHROPIC_API_KEY if not already set"
echo "   2. Start the service: python main.py"
echo "   3. Test the service: python test_service.py"
echo "   4. View documentation: cat README.md"
echo ""
echo "🔗 The service will run on: http://localhost:8000"
echo "📚 API docs will be at: http://localhost:8000/docs"
