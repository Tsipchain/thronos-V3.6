# Thronos Network Branding Guidelines

## Official Taglines

- **Primary**: "Pledge to the unburnable"
- **Secondary**: "Strength in every link, light in every Block"
- **Slogan**: "THR • Pledge to the unburnable • Strength in every Block"

## Color Palette

### Primary Colors
```css
/* Green Spectrum */
--text-primary: #00ff00        /* Bright Green */
--text-secondary: #00ff66      /* Green Glow */
--border-glow: #00ff66         /* Glowing Border */
--circuit-green: #1a3b2e       /* Circuit Board Green */

/* Gold Spectrum */
--gold: #ffd700                /* Primary Gold */
--gold-light: #ffed4e          /* Light Gold */
--gold-dark: #d4af37           /* Dark Gold */

/* Dark Spectrum */
--bg-dark: #000000             /* Pure Black */
--bg-panel: #0a0a0a            /* Panel Background */
--bg-secondary: #111111        /* Secondary Background */

/* Accent Colors */
--accent: #ff6600              /* Fire Orange */
--text-muted: #666666          /* Muted Gray */
```

### Gradient Combinations

#### Title Gradient (Gold to Green)
```css
background: linear-gradient(135deg, #ffd700 0%, #00ff00 50%, #ffed4e 100%);
-webkit-background-clip: text;
-webkit-text-fill-color: transparent;
```

#### Background Gradient
```css
background: linear-gradient(135deg, #000000 0%, #0a0a0a 50%, #000000 100%);
```

#### Border Gradient (Gold-Green-Gold)
```css
border-image: linear-gradient(90deg, #d4af37 0%, #00ff66 50%, #ffd700 100%) 1;
```

## Typography

### Fonts
- **Primary**: `'Courier New', monospace`
- **Character**: Monospace, technical, blockchain-inspired

### Text Styles

#### Headings
```css
h1, h2, h3 {
    background: linear-gradient(135deg, #ffd700 0%, #00ff00 50%, #ffed4e 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: bold;
    letter-spacing: 1px;
    text-transform: uppercase;
}
```

#### Taglines
```css
.tagline {
    color: #00ff66;
    font-size: 10px-12px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    opacity: 0.8;
}
```

## Logo Usage

### Coin Designs

We have two main coin designs:

1. **THR Token Coin**
   - Features: Infinity chain symbol (∞) with "THR" text
   - Background: Circuit board pattern in green
   - Text: "Pledge to the unburnable • Strength in every link, light in every Block"
   - Border: Gold rim with circuit pattern

2. **Thronos Chain Coin**
   - Features: Bitcoin symbol on throne with crown/rays
   - Text: "THRONOS • CHAIN • 2025"
   - Border: Gold rim with decorative elements
   - Style: Regal, powerful, authoritative

### Icon Sizes

Required sizes for all platforms:
- 16x16px - Browser favicon, small icons
- 32x32px - Browser extension toolbar
- 48x48px - Extension popup, small displays
- 128x128px - Extension store listing, large displays
- 256x256px - Marketing materials
- 512x512px - High-resolution displays
- 1024x1024px - Original artwork, print materials

### Logo Effects

#### Glow Effect
```css
filter: drop-shadow(0 0 8px #ffd700) drop-shadow(0 0 12px #00ff66);
```

#### Pulse Animation
```css
@keyframes logo-pulse {
    0%, 100% {
        filter: drop-shadow(0 0 8px #ffd700) drop-shadow(0 0 12px #00ff66);
    }
    50% {
        filter: drop-shadow(0 0 16px #ffed4e) drop-shadow(0 0 20px #00ff66);
    }
}
animation: logo-pulse 3s ease-in-out infinite;
```

#### Float Animation
```css
@keyframes logo-float {
    0%, 100% {
        transform: translateY(0px);
    }
    50% {
        transform: translateY(-10px);
    }
}
animation: logo-float 3s ease-in-out infinite;
```

## UI Components

### Buttons

#### Primary Button
```css
.btn-primary {
    background: linear-gradient(135deg, #00ff00 0%, #00ff66 100%);
    color: #000000;
    border: 2px solid #00ff66;
    box-shadow: 0 0 15px rgba(0, 255, 102, 0.3), inset 0 0 10px rgba(0, 255, 102, 0.1);
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}

.btn-primary:hover {
    background: linear-gradient(135deg, #00ff66 0%, #ffed4e 100%);
    border-color: #ffd700;
    box-shadow: 0 0 25px rgba(255, 215, 0, 0.4), inset 0 0 15px rgba(0, 255, 102, 0.2);
    transform: translateY(-1px);
}
```

### Cards/Panels

#### Token Card
```css
.token-item {
    background: linear-gradient(135deg, rgba(10, 10, 10, 0.8) 0%, rgba(26, 59, 46, 0.1) 100%);
    border: 1px solid #1a3b2e;
    border-radius: 8px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.token-item:hover {
    background: linear-gradient(135deg, rgba(26, 59, 46, 0.3) 0%, rgba(10, 10, 10, 0.9) 100%);
    border-color: #00ff66;
    box-shadow: 0 0 20px rgba(0, 255, 102, 0.2), inset 0 0 10px rgba(0, 255, 102, 0.05);
    transform: translateY(-2px);
}
```

### Headers

```css
.header {
    background: linear-gradient(135deg, #0a0a0a 0%, #111111 50%, #0a0a0a 100%);
    border-bottom: 2px solid;
    border-image: linear-gradient(90deg, #d4af37, #00ff66, #d4af37) 1;
    box-shadow: 0 2px 20px rgba(0, 255, 102, 0.1);
}
```

## Animations

### Glow Pulse
```css
@keyframes balance-glow {
    0%, 100% {
        filter: drop-shadow(0 0 10px rgba(0, 255, 102, 0.4));
    }
    50% {
        filter: drop-shadow(0 0 20px rgba(255, 215, 0, 0.5));
    }
}
```

### Shimmer Effect
```css
.shimmer::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 215, 0, 0.1), transparent);
    animation: shimmer 2s infinite;
}

@keyframes shimmer {
    to {
        left: 100%;
    }
}
```

## Usage Examples

### Chrome Extension Header
```html
<div class="wallet-header">
    <div class="wallet-logo">
        <img src="icons/icon48.png" alt="Thronos">
        <div class="wallet-branding">
            <span class="wallet-title">THRONOS</span>
            <span class="wallet-tagline">Pledge to the unburnable</span>
        </div>
    </div>
</div>
```

### Welcome Screen
```html
<div class="welcome-message">
    <h2>Welcome to Thronos Network</h2>
    <p class="tagline">Strength in every link • Light in every Block</p>
    <p class="subtitle">Connect your wallet to get started</p>
</div>
```

### Balance Display
```html
<div class="total-balance">
    <div class="balance-label">Total Balance</div>
    <div class="balance-amount">1,234.56 THR</div>
</div>
```

## Platform-Specific Guidelines

### Web Application (base.html)
- Use gradient borders for premium feel
- Implement hover effects with glow
- Balance widget should use gold accents
- Maintain circuit board aesthetic in backgrounds

### Chrome Extension
- Compact 380px width
- Large glowing logo (32px)
- Gradient text for title
- Animated balance displays

### Mobile SDK
- Scale logo appropriately for device
- Use native gold/green color schemes
- Implement platform-specific shadows/glows
- Maintain brand consistency across iOS/Android

## Best Practices

1. **Always use gradients** for primary text and important elements
2. **Implement glow effects** on interactive elements
3. **Use animations sparingly** but effectively (2-3 second loops)
4. **Maintain high contrast** for accessibility
5. **Test on dark backgrounds** as primary use case
6. **Use circuit board patterns** subtly in backgrounds
7. **Gold accents** for premium features, green for primary actions
8. **Monospace fonts** for blockchain/technical feel

## Don'ts

- ❌ Don't use flat colors without gradients for headings
- ❌ Don't mix fonts - stick to Courier New
- ❌ Don't use colors outside the palette
- ❌ Don't create logos without glow effects
- ❌ Don't use light backgrounds (breaks brand aesthetic)
- ❌ Don't over-animate (max 3s loops, subtle movements)
- ❌ Don't use comic sans or playful fonts

## Assets Location

- **Logos**: `/static/img/logos/`
- **Icons**: `/chrome-extension/icons/`, `/mobile-sdk/assets/`
- **Documentation**: `/static/img/logos/README.md`

## Version History

- **v1.0** (2025-01-26) - Initial branding guidelines
  - Established color palette
  - Created coin designs
  - Defined typography standards
  - Set animation guidelines
