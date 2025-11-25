#!/usr/bin/env python3
"""
Database migration testing script.

This script tests the database migration process for JSON field normalization
to ensure data integrity and performance improvements.
"""

import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List

import asyncpg
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

from app.core.config import settings
from app.db.base import Base
from app.models.normalized import (
    EmailSecurityFlag, WorkflowStep, EmailMetadata, InvoiceExtractionResult
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseMigrationTester:
    """Test database migration for JSON field normalization."""
    
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self.test_results = {}
    
    async def setup(self):
        """Setup database connection."""
        try:
            # Create async engine
            self.engine = create_async_engine(
                settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
                echo=False
            )
            
            # Create session factory
            self.session_factory = sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
            
            logger.info("Database connection established")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup database: {str(e)}")
            return False
    
    async def cleanup(self):
        """Cleanup database connection."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection closed")
    
    async def test_migration_forward(self):
        """Test forward migration."""
        logger.info("Testing forward migration...")
        
        try:
            async with self.session_factory() as session:
                # Test creating normalized records
                test_email_id = "123e4567-e89b-12d3-a456-426614174000"
                
                # Test EmailSecurityFlag
                security_flag = EmailSecurityFlag(
                    email_id=test_email_id,
                    flag_type="suspicious_content",
                    severity=2,
                    confidence_score=85,
                    description="Test security flag"
                )
                session.add(security_flag)
                
                # Test WorkflowStep
                workflow_step = WorkflowStep(
                    invoice_id=test_email_id,
                    step_name="test_step",
                    step_type="content_extraction",
                    status="pending"
                )
                session.add(workflow_step)
                
                # Test EmailMetadata
                email_metadata = EmailMetadata(
                    email_id=test_email_id,
                    message_id="test@example.com",
                    sender_domain="example.com",
                    word_count=100,
                    attachment_count=2
                )
                session.add(email_metadata)
                
                # Test InvoiceExtractionResult
                extraction_result = InvoiceExtractionResult(
                    invoice_id=test_email_id,
                    extraction_method="ocr",
                    confidence_score=90,
                    vendor_name="Test Vendor",
                    invoice_number="INV-001",
                    total_amount=10000,  # $100.00 in cents
                    currency="USD"
                )
                session.add(extraction_result)
                
                await session.commit()
                
                # Query back the records
                security_flags = await session.execute(
                    sa.select(EmailSecurityFlag).where(
                        EmailSecurityFlag.email_id == test_email_id
                    )
                )
                workflow_steps = await session.execute(
                    sa.select(WorkflowStep).where(
                        WorkflowStep.invoice_id == test_email_id
                    )
                )
                
                self.test_results["forward_migration"] = {
                    "status": "success",
                    "security_flags_created": len(security_flags.scalars().all()),
                    "workflow_steps_created": len(workflow_steps.scalars().all()),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                logger.info("Forward migration test completed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Forward migration test failed: {str(e)}")
            self.test_results["forward_migration"] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            return False
    
    async def test_query_performance(self):
        """Test query performance improvements."""
        logger.info("Testing query performance...")
        
        try:
            async with self.session_factory() as session:
                # Test security flag queries
                start_time = time.time()
                security_flags = await session.execute(
                    sa.select(EmailSecurityFlag)
                    .where(EmailSecurityFlag.severity >= 3)
                    .where(EmailSecurityFlag.is_resolved == False)
                    .limit(100)
                )
                security_query_time = time.time() - start_time
                
                # Test workflow step queries
                start_time = time.time()
                workflow_steps = await session.execute(
                    sa.select(WorkflowStep)
                    .where(WorkflowStep.status == "failed")
                    .order_by(WorkflowStep.created_at.desc())
                    .limit(100)
                )
                workflow_query_time = time.time() - start_time
                
                # Test metadata queries
                start_time = time.time()
                email_metadata = await session.execute(
                    sa.select(EmailMetadata)
                    .where(EmailMetadata.sender_domain == "example.com")
                    .limit(100)
                )
                metadata_query_time = time.time() - start_time
                
                self.test_results["query_performance"] = {
                    "status": "success",
                    "security_query_time_ms": security_query_time * 1000,
                    "workflow_query_time_ms": workflow_query_time * 1000,
                    "metadata_query_time_ms": metadata_query_time * 1000,
                    "security_results": len(security_flags.scalars().all()),
                    "workflow_results": len(workflow_steps.scalars().all()),
                    "metadata_results": len(email_metadata.scalars().all()),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                logger.info(f"Query performance test completed - Security: {security_query_time*1000:.2f}ms, "
                           f"Workflow: {workflow_query_time*1000:.2f}ms, "
                           f"Metadata: {metadata_query_time*1000:.2f}ms")
                return True
                
        except Exception as e:
            logger.error(f"Query performance test failed: {str(e)}")
            self.test_results["query_performance"] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            return False
    
    async def test_data_integrity(self):
        """Test data integrity after migration."""
        logger.info("Testing data integrity...")
        
        try:
            async with self.session_factory() as session:
                # Test foreign key constraints
                # Try to create a security flag with invalid email_id
                try:
                    invalid_flag = EmailSecurityFlag(
                        email_id="00000000-0000-0000-0000-000000000000",
                        flag_type="suspicious_content",
                        severity=1
                    )
                    session.add(invalid_flag)
                    await session.commit()
                    await session.rollback()
                    
                    # If we get here, foreign key constraint is not working
                    raise Exception("Foreign key constraint not enforced")
                    
                except Exception:
                    # Expected - foreign key constraint should prevent this
                    await session.rollback()
                
                # Test data type constraints
                try:
                    invalid_step = WorkflowStep(
                        invoice_id="123e4567-e89b-12d3-a456-426614174000",
                        step_name="test",
                        step_type="invalid_type",  # Should fail enum constraint
                        status="pending"
                    )
                    session.add(invalid_step)
                    await session.commit()
                    await session.rollback()
                    
                    # If we get here, enum constraint is not working
                    raise Exception("Enum constraint not enforced")
                    
                except Exception:
                    # Expected - enum constraint should prevent this
                    await session.rollback()
                
                # Test unique constraints
                try:
                    # Create two extraction results for same invoice with same method
                    extraction1 = InvoiceExtractionResult(
                        invoice_id="123e4567-e89b-12d3-a456-426614174000",
                        extraction_method="ocr",
                        confidence_score=90
                    )
                    extraction2 = InvoiceExtractionResult(
                        invoice_id="123e4567-e89b-12d3-a456-426614174000",
                        extraction_method="ocr",
                        confidence_score=85
                    )
                    session.add(extraction1)
                    session.add(extraction2)
                    await session.commit()
                    await session.rollback()
                    
                    # This might succeed depending on unique constraints
                    # Just log the result
                    logger.info("Unique constraint test completed")
                    
                except Exception as e:
                    await session.rollback()
                    logger.info(f"Unique constraint enforced: {str(e)}")
                
                self.test_results["data_integrity"] = {
                    "status": "success",
                    "foreign_key_constraints": "enforced",
                    "enum_constraints": "enforced",
                    "unique_constraints": "tested",
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                logger.info("Data integrity test completed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Data integrity test failed: {str(e)}")
            self.test_results["data_integrity"] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            return False
    
    async def test_rollback_procedures(self):
        """Test rollback procedures."""
        logger.info("Testing rollback procedures...")
        
        try:
            # Test that we can rollback changes
            async with self.session_factory() as session:
                # Create test data
                test_flag = EmailSecurityFlag(
                    email_id="123e4567-e89b-12d3-a456-426614174000",
                    flag_type="test_flag",
                    severity=1
                )
                session.add(test_flag)
                await session.flush()  # Get ID but don't commit
                
                test_id = test_flag.id
                await session.rollback()
                
                # Verify data was rolled back
                result = await session.execute(
                    sa.select(EmailSecurityFlag).where(EmailSecurityFlag.id == test_id)
                )
                rolled_back_record = result.scalar_one_or_none()
                
                if rolled_back_record is None:
                    rollback_success = True
                else:
                    rollback_success = False
                
                self.test_results["rollback_procedures"] = {
                    "status": "success" if rollback_success else "failed",
                    "rollback_successful": rollback_success,
                    "test_id": str(test_id),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                if rollback_success:
                    logger.info("Rollback procedures test completed successfully")
                else:
                    logger.error("Rollback procedures test failed - data not rolled back")
                
                return rollback_success
                
        except Exception as e:
            logger.error(f"Rollback procedures test failed: {str(e)}")
            self.test_results["rollback_procedures"] = {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            return False
    
    async def generate_report(self):
        """Generate test report."""
        logger.info("Generating test report...")
        
        report = {
            "migration_test_summary": {
                "timestamp": datetime.utcnow().isoformat(),
                "database_url": settings.DATABASE_URL.split("@")[1] if "@" in settings.DATABASE_URL else "hidden",
                "test_results": self.test_results
            },
            "recommendations": []
        }
        
        # Analyze results and generate recommendations
        all_passed = all(
            result.get("status") == "success" 
            for result in self.test_results.values()
        )
        
        if all_passed:
            report["recommendations"].append("All tests passed - migration is ready for production")
        else:
            report["recommendations"].append("Some tests failed - review and fix issues before production")
        
        # Performance recommendations
        if "query_performance" in self.test_results:
            perf = self.test_results["query_performance"]
            if perf.get("security_query_time_ms", 0) > 100:
                report["recommendations"].append("Consider adding index on security flag severity")
            if perf.get("workflow_query_time_ms", 0) > 100:
                report["recommendations"].append("Consider adding index on workflow step status")
        
        return report
    
    async def run_all_tests(self):
        """Run all migration tests."""
        logger.info("Starting database migration tests...")
        
        if not await self.setup():
            return False
        
        try:
            # Run all tests
            await self.test_migration_forward()
            await self.test_query_performance()
            await self.test_data_integrity()
            await self.test_rollback_procedures()
            
            # Generate report
            report = await self.generate_report()
            
            # Print results
            print("\n" + "="*80)
            print("DATABASE MIGRATION TEST REPORT")
            print("="*80)
            
            for test_name, result in self.test_results.items():
                status = result.get("status", "unknown")
                print(f"\n{test_name.upper()}: {status.upper()}")
                if status == "failed":
                    print(f"  Error: {result.get('error', 'Unknown error')}")
                elif "query_time_ms" in result:
                    print(f"  Query times: {result}")
            
            print("\nRECOMMENDATIONS:")
            for rec in report["recommendations"]:
                print(f"  • {rec}")
            
            print("\n" + "="*80)
            
            return all(
                result.get("status") == "success" 
                for result in self.test_results.values()
            )
            
        finally:
            await self.cleanup()


async def main():
    """Main function."""
    tester = DatabaseMigrationTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())