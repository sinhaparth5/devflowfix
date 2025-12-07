#!/usr/bin/env python3
"""
Test script to verify solution generation from NVIDIA API.

This script tests the complete flow:
1. Error received from GitHub
2. Analyzed by NVIDIA LLM
3. Solutions generated and logged to console
"""

import asyncio
import json
from app.adapters.ai.nvidia.llm import LLMAdapter
from app.core.enums import FailureType

async def test_solution_generation():
    """Test solution generation for a GitHub Actions failure."""
    
    # Initialize LLM adapter
    llm = LLMAdapter(
        temperature=0.2,
        max_tokens=3000,
    )
    
    try:
        # Test case: npm dependency resolution failure
        error_log = """npm ERR! code ETIMEDOUT
npm ERR! errno ETIMEDOUT
npm ERR! syscall connect
npm ERR! network request to https://registry.npmjs.org failed, reason: connect ETIMEDOUT
npm ERR! network This is a problem related to network connectivity.
npm ERR! network In most cases you are behind a proxy or have bad network settings.
npm ERR! network 
npm ERR! network If you are behind a proxy, please make sure that the
npm ERR! network    proxy config in npm is set properly.  See: 'npm help config'

npm ERR! A complete log of this run can be found in:
npm ERR!     /home/runner/.npm/_logs/2025-12-07T12_22_31_405Z-debug-0.log"""

        failure_type = "buildfailure"
        root_cause = "NPM registry timeout during dependency resolution"
        
        context = {
            "source": "github",
            "repository": "Shine-5705/DevflowFix-tester",
            "branch": "main",
            "workflow": "CI/CD Pipeline",
            "step": "npm install",
            "environment": "github_actions",
        }
        
        print("\n" + "="*80)
        print("TESTING SOLUTION GENERATION")
        print("="*80)
        print(f"\n📊 Input:")
        print(f"   Failure Type: {failure_type}")
        print(f"   Root Cause: {root_cause}")
        print(f"   Repository: {context.get('repository')}")
        
        print(f"\n🔄 Generating solutions from NVIDIA LLM...")
        print("This may take 10-30 seconds...\n")
        
        # Generate solutions
        solution = await llm.generate_solution(
            error_log=error_log,
            failure_type=failure_type,
            root_cause=root_cause,
            context=context,
            repository_code=None,
        )
        
        # Print the raw solution JSON for debugging
        print("\n📋 Raw Solution Response:")
        print("-" * 80)
        print(json.dumps(solution, indent=2))
        print("-" * 80)
        
        # Format and display solutions nicely
        print("\n✅ FORMATTED SOLUTION")
        print("="*80)
        
        if solution.get("immediate_fix"):
            print("\n📋 Immediate Fix:")
            fix = solution["immediate_fix"]
            print(f"   Description: {fix.get('description')}")
            print(f"   Estimated Time: {fix.get('estimated_time_minutes')} minutes")
            print(f"   Risk Level: {fix.get('risk_level')}")
            print(f"   Steps:")
            for i, step in enumerate(fix.get("steps", []), 1):
                print(f"      {i}. {step}")
        
        if solution.get("code_changes"):
            print(f"\n📝 Code Changes:")
            code = solution["code_changes"]
            print(f"   File: {code.get('file_path')}")
            print(f"   Explanation: {code.get('explanation')}")
        
        if solution.get("configuration_changes"):
            print(f"\n⚙️  Configuration Changes:")
            for cfg in solution.get("configuration_changes", []):
                print(f"   File: {cfg.get('file')}")
                print(f"   Setting: {cfg.get('setting')}")
                print(f"   Value: {cfg.get('current_value')} → {cfg.get('recommended_value')}")
        
        if solution.get("prevention_measures"):
            print(f"\n🛡️  Prevention Measures:")
            for measure in solution.get("prevention_measures", []):
                print(f"   - {measure.get('measure')}")
        
        print("\n" + "="*80)
        print("✨ Solution generation completed successfully!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error during solution generation:")
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        await llm.close()


if __name__ == "__main__":
    asyncio.run(test_solution_generation())
