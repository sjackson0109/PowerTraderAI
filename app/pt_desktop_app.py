"""
Phase 4 Desktop GUI Integration Script

This script modifies the existing PowerTrader Hub to add Phase 4 trading functionality.
It adds new tabs to the logs notebook for Trading Control, Risk Management, and Cost Analysis.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pt_gui_integration import (
    integrate_phase4_gui,
    TradingControlPanel,
    RiskManagementPanel, 
    CostAnalysisPanel
)

def integrate_with_powertrader_hub():
    """
    Integrate Phase 4 systems with the existing PowerTrader Hub.
    This function patches the existing hub to add our new functionality.
    """
    try:
        # Import the existing hub
        from pt_hub import PowerTraderHub
        
        # Store the original _build_layout method
        original_build_layout = PowerTraderHub._build_layout
        
        def enhanced_build_layout(self):
            """Enhanced layout with Phase 4 integration."""
            # Call the original layout builder
            original_build_layout(self)
            
            # Add Phase 4 tabs to the logs notebook
            if hasattr(self, 'logs_nb'):
                try:
                    # Add Trading Control tab
                    trading_tab = TradingControlPanel(self.logs_nb)
                    self.logs_nb.add(trading_tab, text="Trading Control")
                    self.trading_control = trading_tab
                    
                    # Add Risk Management tab
                    risk_tab = RiskManagementPanel(self.logs_nb)
                    self.logs_nb.add(risk_tab, text="Risk Management")
                    self.risk_management = risk_tab
                    
                    # Add Cost Analysis tab
                    cost_tab = CostAnalysisPanel(self.logs_nb)
                    self.logs_nb.add(cost_tab, text="Cost Analysis")
                    self.cost_analysis = cost_tab
                    
                    print("✓ Phase 4 GUI integration successful!")
                    
                except Exception as e:
                    print(f"✗ Phase 4 GUI integration failed: {e}")
        
        # Monkey patch the enhanced method
        PowerTraderHub._build_layout = enhanced_build_layout
        
        return True
        
    except Exception as e:
        print(f"Failed to integrate with PowerTrader Hub: {e}")
        return False

if __name__ == "__main__":
    print("PowerTrader AI - Phase 4 Desktop GUI Integration")
    print("=" * 50)
    
    # Apply the integration
    success = integrate_with_powertrader_hub()
    
    if success:
        print("\\nStarting PowerTrader Hub with Phase 4 features...")
        
        try:
            from pt_hub import PowerTraderHub
            
            # Start the enhanced GUI
            app = PowerTraderHub()
            app.mainloop()
            
        except KeyboardInterrupt:
            print("\\nShutdown requested by user")
        except Exception as e:
            print(f"\\nApplication error: {e}")
    else:
        print("\\nFailed to integrate Phase 4 features. Please check dependencies.")
        sys.exit(1)