import Contacts
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

let store = CNContactStore()
let status = CNContactStore.authorizationStatus(for: .contacts)
if status == .denied || status == .restricted {
    fail("Contacts permission is unavailable")
}
if status == .notDetermined {
    let semaphore = DispatchSemaphore(value: 0)
    var granted = false
    store.requestAccess(for: .contacts) { allowed, _ in
        granted = allowed
        semaphore.signal()
    }
    semaphore.wait()
    if !granted { fail("Contacts permission was not granted") }
}

let keys: [CNKeyDescriptor] = [
    CNContactIdentifierKey as CNKeyDescriptor,
    CNContactFormatter.descriptorForRequiredKeys(for: .fullName),
    CNContactNicknameKey as CNKeyDescriptor,
    CNContactPhoneNumbersKey as CNKeyDescriptor,
    CNContactEmailAddressesKey as CNKeyDescriptor,
]
let request = CNContactFetchRequest(keysToFetch: keys)
request.unifyResults = true
var contacts: [[String: Any]] = []

do {
    try store.enumerateContacts(with: request) { contact, _ in
        let displayName = CNContactFormatter.string(from: contact, style: .fullName) ?? ""
        if displayName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return }
        let phones = contact.phoneNumbers.map { value in
            ["label": CNLabeledValue<NSString>.localizedString(forLabel: value.label ?? ""),
             "value": value.value.stringValue]
        }
        let emails = contact.emailAddresses.map { value in
            ["label": CNLabeledValue<NSString>.localizedString(forLabel: value.label ?? ""),
             "value": value.value as String]
        }
        contacts.append([
            "identifier": contact.identifier,
            "display_name": displayName,
            "nickname": contact.nickname,
            "phones": phones,
            "emails": emails,
        ])
    }
} catch {
    fail("Contacts enumeration failed")
}

do {
    let data = try JSONSerialization.data(withJSONObject: ["contacts": contacts], options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
} catch {
    fail("Contacts serialization failed")
}
