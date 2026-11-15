import { ErrorCode, McpError } from '../errors.js';
import type { MauticApiClient } from '../api/client.js';
import type { ToolDefinition, ToolHandler } from '../types/index.js';
import {
  flattenContactPayload,
  normalizeTagList,
  verifyContactTags,
} from '../lib/contact-payload.js';

const CUSTOM_FIELDS_DESCRIPTION =
  'Custom field values, keyed by Mautic field alias. Each entry is flattened to a top-level contact property ' +
  'before the request is sent (for example {"tags": ["a"]} is sent as "tags": ["a"]).';

export const toolDefinitions: ToolDefinition[] = [
  {
    name: 'create_contact',
    description: 'Create a new contact in Mautic',
    inputSchema: {
      type: 'object',
      properties: {
        email: { type: 'string', description: 'Contact email address' },
        firstName: { type: 'string', description: 'First name' },
        lastName: { type: 'string', description: 'Last name' },
        phone: { type: 'string', description: 'Phone number' },
        company: { type: 'string', description: 'Company name' },
        position: { type: 'string', description: 'Job position' },
        customFields: { type: 'object', description: CUSTOM_FIELDS_DESCRIPTION },
      },
      required: ['email'],
    },
  },
  {
    name: 'update_contact',
    description: 'Update an existing contact',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'number', description: 'Contact ID' },
        email: { type: 'string', description: 'Contact email address' },
        firstName: { type: 'string', description: 'First name' },
        lastName: { type: 'string', description: 'Last name' },
        phone: { type: 'string', description: 'Phone number' },
        company: { type: 'string', description: 'Company name' },
        position: { type: 'string', description: 'Job position' },
        customFields: { type: 'object', description: CUSTOM_FIELDS_DESCRIPTION },
      },
      required: ['id'],
    },
  },
  {
    name: 'get_contact',
    description: 'Get contact details by ID or email',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'number', description: 'Contact ID' },
        email: { type: 'string', description: 'Contact email address' },
      },
    },
  },
  {
    name: 'search_contacts',
    description: 'Search contacts with filters and pagination',
    inputSchema: {
      type: 'object',
      properties: {
        search: { type: 'string', description: 'Search term' },
        limit: { type: 'number', description: 'Number of results (max 200)', maximum: 200 },
        start: { type: 'number', description: 'Starting offset for pagination' },
        orderBy: { type: 'string', description: 'Field to order by' },
        orderByDir: { type: 'string', enum: ['ASC', 'DESC'], description: 'Order direction' },
        publishedOnly: { type: 'boolean', description: 'Only published contacts' },
        minimal: { type: 'boolean', description: 'Return minimal contact data' },
      },
    },
  },
  {
    name: 'delete_contact',
    description: 'Delete a contact from Mautic',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'number', description: 'Contact ID to delete' },
      },
      required: ['id'],
    },
  },
  {
    name: 'add_contact_to_segment',
    description: 'Add a contact to a specific segment',
    inputSchema: {
      type: 'object',
      properties: {
        contactId: { type: 'number', description: 'Contact ID' },
        segmentId: { type: 'number', description: 'Segment ID' },
      },
      required: ['contactId', 'segmentId'],
    },
  },
];

export const toolHandlers: Record<string, ToolHandler> = {
  async create_contact(client: MauticApiClient, args: any) {
    const payload = flattenContactPayload(args);
    if (typeof payload.email !== 'string' || payload.email.trim() === '') {
      throw new McpError(ErrorCode.InvalidParams, 'create_contact: email is required');
    }
    const requestedTags = normalizeTagList(payload.tags);

    const response = await client.v1.post('/contacts/new', payload);
    const contact = response?.data?.contact ?? {};
    const contactId = contact?.id;

    let confirmedTags: string[] = [];
    if (requestedTags.length > 0) {
      if (contactId === undefined || contactId === null) {
        throw new McpError(
          ErrorCode.InternalError,
          'create_contact: the provider created the contact but returned no id, so the requested tags could not be ' +
            'verified by read-back. Do not report this as success.',
        );
      }
      confirmedTags = await verifyContactTags(client, contactId, requestedTags, 'create_contact');
    }

    const tagLine =
      requestedTags.length > 0
        ? `\nConfirmed tags (read back): ${JSON.stringify(confirmedTags)}`
        : '';
    return {
      content: [
        {
          type: 'text',
          text: `Contact created successfully:\n${JSON.stringify(contact, null, 2)}${tagLine}`,
        },
      ],
    };
  },

  async update_contact(client: MauticApiClient, args: any) {
    const { id } = args ?? {};
    if (id === undefined || id === null) {
      throw new McpError(ErrorCode.InvalidParams, 'update_contact: id is required');
    }
    const payload = flattenContactPayload(args, { omit: ['id'] });
    if (Object.keys(payload).length === 0) {
      throw new McpError(
        ErrorCode.InvalidParams,
        'update_contact: at least one field besides id must be provided',
      );
    }
    const requestedTags = normalizeTagList(payload.tags);

    const response = await client.v1.patch(`/contacts/${id}/edit`, payload);

    let confirmedTags: string[] = [];
    if (requestedTags.length > 0) {
      confirmedTags = await verifyContactTags(client, id, requestedTags, 'update_contact');
    }

    const tagLine =
      requestedTags.length > 0
        ? `\nConfirmed tags (read back): ${JSON.stringify(confirmedTags)}`
        : '';
    return {
      content: [
        {
          type: 'text',
          text: `Contact updated successfully:\n${JSON.stringify(response?.data?.contact, null, 2)}${tagLine}`,
        },
      ],
    };
  },

  async get_contact(client: MauticApiClient, args: any) {
    const { id, email } = args;
    let response;

    if (id) {
      response = await client.v1.get(`/contacts/${id}`);
    } else if (email) {
      const searchResponse = await client.v1.get('/contacts', {
        params: { search: `email:${email}`, limit: 1 }
      });
      if (searchResponse.data.total === 0) {
        return { content: [{ type: 'text', text: `No contact found with email: ${email}` }] };
      }
      const contactId = Object.keys(searchResponse.data.contacts)[0];
      response = await client.v1.get(`/contacts/${contactId}`);
    } else {
      throw new McpError(ErrorCode.InvalidParams, 'Either id or email must be provided');
    }

    return {
      content: [{ type: 'text', text: `Contact details:\n${JSON.stringify(response.data.contact, null, 2)}` }],
    };
  },

  async search_contacts(client: MauticApiClient, args: any) {
    const params: any = {};
    if (args?.search) params.search = args.search;
    if (args?.limit) params.limit = Math.min(args.limit, 200);
    if (args?.start) params.start = args.start;
    if (args?.orderBy) params.orderBy = args.orderBy;
    if (args?.orderByDir) params.orderByDir = args.orderByDir;
    if (args?.publishedOnly) params.publishedOnly = args.publishedOnly;
    if (args?.minimal) params.minimal = args.minimal;

    const response = await client.v1.get('/contacts', { params });
    return {
      content: [{ type: 'text', text: `Found ${response.data.total} contacts:\n${JSON.stringify(response.data.contacts, null, 2)}` }],
    };
  },

  async delete_contact(client: MauticApiClient, args: any) {
    const { id } = args;
    await client.v1.delete(`/contacts/${id}/delete`);
    return { content: [{ type: 'text', text: `Contact ${id} deleted successfully` }] };
  },

  async add_contact_to_segment(client: MauticApiClient, args: any) {
    const { contactId, segmentId } = args;
    await client.v1.post(`/segments/${segmentId}/contact/${contactId}/add`);
    return {
      content: [{ type: 'text', text: `Contact ${contactId} added to segment ${segmentId} successfully` }],
    };
  },
};
