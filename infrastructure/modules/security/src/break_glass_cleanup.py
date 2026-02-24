import boto3
import os
import logging
import json
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
TABLE_NAME = os.environ.get('REGISTRY_TABLE_NAME', 'a-ponte-registry')

def handler(event, context):
    """
    Lambda invocada pelo EventBridge Scheduler para revogar acesso Break Glass.
    Espera receber o payload com o ProjectName.
    """
    logger.info(f"Event received: {json.dumps(event)}")

    project_name = event.get('ProjectName')
    if not project_name:
        logger.error("ProjectName not provided in event payload.")
        return {"status": "error", "message": "ProjectName missing"}

    table = dynamodb.Table(TABLE_NAME)

    try:
        # Atualiza o registro para desativar o Break Glass
        # Remove SessionId e Expiration, e seta Active como False
        response = table.update_item(
            Key={'ProjectName': project_name},
            UpdateExpression="REMOVE BreakGlassSessionId, BreakGlassExpiration SET BreakGlassActive = :false, UpdatedAt = :now",
            ExpressionAttributeValues={
                ':false': False,
                ':now': datetime.utcnow().isoformat()
            },
            ReturnValues="UPDATED_NEW"
        )

        logger.info(f"Break Glass revoked for {project_name}. Response: {response}")
        return {"status": "success", "project": project_name, "action": "revoked"}

    except Exception as e:
        logger.error(f"Failed to revoke Break Glass for {project_name}: {str(e)}")
        raise e
