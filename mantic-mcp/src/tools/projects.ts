import type { MauticApiClient } from '../api/client.js';
import type { ToolDefinition, ToolHandler } from '../types/index.js';
import { mapV2Error, V2_SURFACE } from '../api/v2-errors.js';

export const toolDefinitions: ToolDefinition[] = [
  {
    name: 'list_projects',
    description: `List all projects - organize marketing resources (${V2_SURFACE})`,
    inputSchema: {
      type: 'object',
      properties: {
        page: { type: 'number', description: 'Page number for pagination' },
        itemsPerPage: { type: 'number', description: 'Items per page (default 30)' },
      },
    },
  },
  {
    name: 'get_project',
    description: 'Get project details by ID (Mautic 7 API v2)',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'number', description: 'Project ID' },
      },
      required: ['id'],
    },
  },
  {
    name: 'create_project',
    description: 'Create a new project to organize marketing resources (Mautic 7 API v2)',
    inputSchema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Project name (required, must be unique)' },
        description: { type: 'string', description: 'Project description' },
        properties: { type: 'object', description: 'Additional JSON properties' },
      },
      required: ['name'],
    },
  },
  {
    name: 'update_project',
    description: 'Fully update an existing project (Mautic 7 API v2)',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'number', description: 'Project ID' },
        name: { type: 'string', description: 'Project name (required, must be unique)' },
        description: { type: 'string', description: 'Project description' },
        properties: { type: 'object', description: 'Additional JSON properties' },
      },
      required: ['id', 'name'],
    },
  },
  {
    name: 'patch_project',
    description: 'Partially update an existing project (Mautic 7 API v2)',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'number', description: 'Project ID' },
        name: { type: 'string', description: 'Project name' },
        description: { type: 'string', description: 'Project description' },
        properties: { type: 'object', description: 'Additional JSON properties' },
      },
      required: ['id'],
    },
  },
  {
    name: 'delete_project',
    description: 'Delete a project (Mautic 7 API v2)',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'number', description: 'Project ID' },
      },
      required: ['id'],
    },
  },
];

export const toolHandlers: Record<string, ToolHandler> = {
  async list_projects(client: MauticApiClient, args: any) {
    const params: any = {};
    if (args?.page) params.page = args.page;
    if (args?.itemsPerPage) params.itemsPerPage = args.itemsPerPage;

    let response;
    try {
      response = await client.v2.get('/projects', { params });
    } catch (error) {
      mapV2Error('list_projects', error);
    }
    const { items, total } = client.parseV2Collection(response.data);
    return {
      content: [{ type: 'text', text: `Found ${total} projects:\n${JSON.stringify(items, null, 2)}` }],
    };
  },

  async get_project(client: MauticApiClient, args: any) {
    const { id } = args;
    let response;
    try {
      response = await client.v2.get(`/projects/${id}`);
    } catch (error) {
      mapV2Error('get_project', error);
    }
    return {
      content: [{ type: 'text', text: `Project details:\n${JSON.stringify(response.data, null, 2)}` }],
    };
  },

  async create_project(client: MauticApiClient, args: any) {
    const payload: any = { name: args.name };
    if (args.description) payload.description = args.description;
    if (args.properties) payload.properties = args.properties;

    let response;
    try {
      response = await client.v2.post('/projects', payload);
    } catch (error) {
      mapV2Error('create_project', error);
    }
    return {
      content: [{ type: 'text', text: `Project created successfully:\n${JSON.stringify(response.data, null, 2)}` }],
    };
  },

  async update_project(client: MauticApiClient, args: any) {
    const { id, ...updateData } = args;
    let response;
    try {
      response = await client.v2.put(`/projects/${id}`, updateData);
    } catch (error) {
      mapV2Error('update_project', error);
    }
    return {
      content: [{ type: 'text', text: `Project ${id} updated successfully:\n${JSON.stringify(response.data, null, 2)}` }],
    };
  },

  async patch_project(client: MauticApiClient, args: any) {
    const { id, ...patchData } = args;
    let response;
    try {
      response = await client.v2.patch(`/projects/${id}`, patchData, {
        headers: { 'Content-Type': 'application/merge-patch+json' },
      });
    } catch (error) {
      mapV2Error('patch_project', error);
    }
    return {
      content: [{ type: 'text', text: `Project ${id} patched successfully:\n${JSON.stringify(response.data, null, 2)}` }],
    };
  },

  async delete_project(client: MauticApiClient, args: any) {
    const { id } = args;
    try {
      await client.v2.delete(`/projects/${id}`);
    } catch (error) {
      mapV2Error('delete_project', error);
    }
    return {
      content: [{ type: 'text', text: `Project ${id} deleted successfully` }],
    };
  },
};
